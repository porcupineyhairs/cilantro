import uuid
import logging
import os

from abc import abstractmethod
from celery import chord, signature

from workers.task_information import get_label, get_description
from utils.celery_client import celery_app
from utils.job_db import JobDb


class BaseJob:
    """Wraps multiple celery task chains as a celery chord and handles ID generation."""

    logger = logging.getLogger(__name__)

    @property
    def job_type(self):
        raise NotImplementedError

    @property
    def label(self):
        raise NotImplementedError

    @property
    def description(self):
        raise NotImplementedError

    def __init__(self):
        self.job_db = JobDb()

    @abstractmethod
    def run(self):
        """
        Trigger asynchronous execution of the job.

        :return AsyncResult: Celery result
        """
        raise NotImplementedError("run method not implemented")

    @abstractmethod
    def _add_to_job_db(self, params, user_name):
        raise NotImplementedError("_add_to_job_db method not implemented")


class BatchJob(BaseJob):

    @abstractmethod
    def _create_chains(self, params, user_name):
        raise NotImplementedError("_create_chains method not implemented")

    def __init__(self, params, user_name):
        """
        Create a job chord and triggers ID generation.

        :param List[chain] chains: A list of celery task chains
        """
        super().__init__()
        self.id = _generate_id()

        (chains, chain_parameters) = self._create_chains(params, user_name)

        self.chain_parameters = chain_parameters

        # Once all job chains have finished within this chord, we have to
        # trigger a callback worker in order to update the database entry
        # for the chord job itself.
        self.chord = chord(chains, signature(
            'finish_chord', kwargs={'job_id': self.id, 'work_path': self.id}))

        self.chain_ids = self._add_to_job_db(params, user_name)

        self.logger.debug(f"created job chord with id: {self.id}: ")
        for (index, chain_id) in enumerate(self.chain_ids, 1):
            self.logger.debug(
                f'  chain #{index}, job id: {chain_id}:')

    def run(self):
        self.job_db.update_job_state(self.id, 'started')
        for chain_id in self.chain_ids:
            self.job_db.update_job_state(chain_id, 'started')

        self.chord.apply_async(task_id=self.id)

    def _add_to_job_db(self, params, user_name):
        chain_ids = []

        for idx, current_chain in enumerate(self.chord.tasks):
            current_chain_links = []
            current_chain_id = _generate_id()
            current_work_path = current_chain_id
            current_chain.kwargs['work_path'] = current_work_path

            for single_task in current_chain.tasks:
                job_id = _generate_id()

                single_task.kwargs['job_id'] = job_id
                single_task.options['task_id'] = job_id
                single_task.kwargs['work_path'] = current_work_path
                single_task.kwargs['parent_job_id'] = current_chain_id
                label = get_label(single_task.name)
                description = get_description(single_task.name)

                self.job_db.add_job(job_id=job_id,
                                    user=user_name,
                                    job_type=single_task.name,
                                    parent_job_id=current_chain_id,
                                    child_job_ids=[],
                                    parameters=single_task.kwargs,
                                    label=label,
                                    description=description)

                current_chain_links += [job_id]

            self.job_db.add_job(job_id=current_chain_id,
                                user=user_name,
                                job_type='cilantro_batch_chain',
                                parent_job_id=self.id,
                                child_job_ids=current_chain_links,
                                parameters=self.chain_parameters[idx],
                                label=self.chain_parameters[idx]['id'],
                                description="Group containing all the individual steps for a single batch.")
            chain_ids += [current_chain_id]

        self.job_db.add_job(job_id=self.id,
                            user=user_name,
                            job_type=self.job_type,
                            parent_job_id=None,
                            child_job_ids=chain_ids,
                            parameters=params,
                            label=self.label,
                            description=self.description)

        return chain_ids


class IngestArchivalMaterialsJob(BatchJob):
    job_type = 'ingest_archival_material'
    label = 'Retrodigitized Archival Material'
    description = "Import multiple folders that contain scans of archival material into iDAI.archives / AtoM."

    def _create_chains(self, params, user_name):
        chains = []
        chain_parameters = []

        for record_target in params['targets']:

            chain_parameters.append(
                record_target
            )

            task_params = dict(**record_target, **{'user': user_name},
                               initial_representation='tif', job_type=self.job_type)

            current_chain = _link('create_object', **task_params)

            current_chain |= _link('list_files',
                                   representation='tif',
                                   target='jpg',
                                   task='convert.tif_to_jpg')

            current_chain |= _link('list_files',
                                   representation='jpg',
                                   target='jpg_thumbnails',
                                   task='convert.tif_to_jpg',
                                   max_width=50,
                                   max_height=50)

            current_chain |= _link('list_files',
                                   representation='tif',
                                   target='ptif',
                                   task='convert.tif_to_ptif')

            if params['options']['ocr_options']['do_ocr']:
                lang = params['options']['ocr_options']['ocr_lang']
            else:
                lang = None

            current_chain |= _link('list_files',
                                   representation='tif',
                                   target='pdf',
                                   task='convert.tif_to_pdf',
                                   ocr_lang=lang)

            current_chain |= _link('convert.merge_converted_pdf')

            current_chain |= _link('convert.set_pdf_metadata',
                                   metadata=self._create_pdf_metadata(record_target['metadata']))

            current_chain |= _link('generate_xml',
                                   template_file='mets_template_archive.xml',
                                   target_filename='mets.xml',
                                   schema_file='mets.xsd')

            current_chain |= _link('publish_to_repository')
            current_chain |= _link('publish_to_atom')
            current_chain |= _link('publish_to_archive')

            current_chain |= _link('cleanup_directories')

            current_chain |= _link(
                'finish_chain',
                success_msg="Material imported successfully",
                chain_input_directory=record_target['path'],
                user_name=user_name
            )

            chains.append(current_chain)

        return (chains, chain_parameters)

    def _create_pdf_metadata(self, metadata):
        pdf_metadata = {}
        if "title" in metadata:
            pdf_metadata["/Title"] = metadata["title"]
        if "atom_id" in metadata:
            pdf_metadata[
                "/ArchiveLink"] = f'https://archives.dainst.org/index.php/{metadata["atom_id"]}'

        if "authors" in metadata and len(metadata["authors"]) != 0:
            authors_string = ""
            count = 0
            for author in metadata['authors']:
                if count != 0:
                    authors_string += ", "
                authors_string += author
                count += 1
            pdf_metadata["/Author"] = authors_string

        subject_string = ""
        if "scope_and_content" in metadata:
            subject_string += f"Eingrenzung und Inhalt:\n{metadata['scope_and_content']}\n\n"

        repository_string = ""
        if "repository" in metadata:
            repository_string += f"Archiv:\n{metadata['repository']}"
        if "repository_inherited_from" in metadata:
            repository_string += f"\nBestand: {metadata['repository_inherited_from']}"
        if repository_string:
            subject_string += f"{repository_string}\n\n"

        if "reference_code" in metadata:
            subject_string += f"Signatur:\n{metadata['reference_code']}\n\n"

        if "creators" in metadata and len(metadata['creators']) != 0:
            creators_string = "Bestandsbildner:\n"
            for creator in metadata['creators']:
                creators_string += f"{creator}\n"
            creators_string += "\n"
            subject_string += creators_string

        if "extent_and_medium" in metadata:
            subject_string += f"Umfang und Medium:\n{metadata['extent_and_medium']}\n\n"

        level_of_description_translations = {
            "Fonds": "Bestand",
            "File": "Akte",
            "Item": "Objekt"
        }

        if "level_of_description" in metadata:
            subject_string += f"Erschließungsstufe: "
            if metadata['level_of_description'] in level_of_description_translations:
                subject_string += level_of_description_translations[metadata['level_of_description']]
            else:
                subject_string += metadata['level_of_description']
            subject_string += "\n\n"

        if "notes" in metadata and len(metadata["notes"]) != 0:
            notes_string = ""
            for note in metadata["notes"]:
                notes_string += f"{note}\n"
            notes_string += "\n"
            subject_string += notes_string

        date_type_translations = {
            "Creation": "Datum",
            "Accumulation": "Laufzeit"
        }
        if "dates" in metadata and len(metadata["dates"]) != 0:
            dates_string = ""
            count = 0
            for date in metadata["dates"]:
                if count != 0:
                    dates_string += " | "

                if date['type'] in date_type_translations:
                    dates_string += f"{date_type_translations[date['type']]}: "
                else:
                    dates_string += f"Datum ({date['type']}): "

                if "start_date" in date and "end_date" in date:
                    if date["start_date"] == date["end_date"]:
                        dates_string += date["start_date"]
                    else:
                        dates_string += f"{date['start_date']} - {date['end_date']}"

                dates_string += "\n"
                count += 1
            subject_string += dates_string

        if metadata['copyright']:
            subject_string += f"\n{metadata['copyright']}"

        pdf_metadata['/Subject'] = subject_string

        return pdf_metadata


class IngestJournalsJob(BatchJob):
    job_type = 'ingest_journals'
    label = 'Retrodigitized Journals'
    description = "Import multiple folders that contain scans of journal issues into iDAI.publications / OJS."

    def _create_chains(self, params, user_name):
        chains = []
        chain_parameters = []

        for issue_target in params['targets']:
            chain_parameters.append(
                issue_target
            )

            article_workdir_prefixes = []
            article_copy_instructions = {}
            for count, article in enumerate(issue_target["metadata"]["articles"]):
                prefix = f"article-{count}_"
                article_workdir_prefixes.append(prefix)
                article_copy_instructions[f"{article['path']}/tif"] = (f"{prefix}tif", "*.tif")

            task_params = dict(
                **issue_target, 
                **{
                    'user': user_name,
                    'copy_instructions':
                    {
                        **{"tif": ("issue_tif", "*.tif")},
                        **article_copy_instructions
                    }
                }
            )

            current_chain = _link('create_complex_object', **task_params)

            if params['options']['ocr_options']['do_ocr']:
                lang = params['options']['ocr_options']['ocr_lang']
            else:
                lang = None

            current_chain = self._add_image_processing_links(current_chain, "issue_", lang)
            
            counter = 0
            for prefix in article_workdir_prefixes:
                current_chain = self._add_image_processing_links(current_chain, prefix, lang)
                counter += 1
            
            current_chain |= _link(
                'generate_xml',
                input_file_directories={
                    "pdfs": ["issue_pdf"] + [f"{prefix}pdf" for prefix in article_workdir_prefixes]
                },
                template_file='ojs3_template_issue.xml',
                target_filename='ojs_import.xml',
            )

            # current_chain |= _link(
            #     'generate_xml',
            #     template_file='mets_template_journal.xml',
            #     target_filename='mets.xml',
            #     schema_file='mets.xsd'
            # )

            current_chain |= _link(
                'publish_to_ojs',
                ojs_journal_code=issue_target['metadata']['ojs_journal_code']
            )

            current_chain |= _link('publish_to_archive')

            current_chain |= _link('cleanup_directories')

            current_chain |= _link(
                'finish_chain',
                success_msg="Journal imported successfully",
                success_url='{}/{}/manageIssues#futureIssues'.format(
                    os.getenv('OJS_BASE_URL'),
                    issue_target['metadata']['ojs_journal_code']
                ),
                success_url_label='View in OJS',
                chain_input_directory=issue_target['path'],
                user_name=user_name
            )
            chains.append(current_chain)

        return (chains, chain_parameters)

    def _add_image_processing_links(self, chain, directory_prefix, ocr_lang):
        chain |= _link(
                'list_files',
                representation=f'{directory_prefix}tif',
                target=f'{directory_prefix}pdf',
                task='convert.tif_to_pdf',
                ocr_lang=ocr_lang
            )

        chain |= _link(
            'convert.merge_converted_pdf',
            input_directory=f'{directory_prefix}pdf'
        )

        chain |= _link(
            'list_files',
            representation=f'{directory_prefix}tif',
            target=f'{directory_prefix}jpg',
            task='convert.tif_to_jpg'
        )

        chain |= _link(
            'list_files',
            representation=f'{directory_prefix}tif',
            target=f'{directory_prefix}jpg_thumbnails',
            task='convert.scale_image',
            max_width=50,
            max_height=50
        )

        return chain


class IngestMonographsJob(BatchJob):
    job_type = 'ingest_monographs'
    label = 'Retrodigitized Monographs'
    description = "Import multiple folders that contain scans of monographs into iDAI.publications / OMP."

    def _create_chains(self, params, user_name):
        chains = []
        chain_parameters = []
        for monograph_target in params['targets']:
            task_params = dict(**monograph_target, **{'user': user_name},
                               initial_representation='tif', job_type=self.job_type)

            chain_parameters.append(
                monograph_target
            )

            current_chain = _link('create_object', **task_params)

            if params['options']['ocr_options']['do_ocr']:
                lang = params['options']['ocr_options']['ocr_lang']
            else:
                lang = None

            current_chain |= _link('list_files',
                                   representation='tif',
                                   target='pdf',
                                   task='convert.tif_to_pdf',
                                   ocr_lang=lang)

            current_chain |= _link('convert.merge_converted_pdf')

            current_chain |= _link('list_files',
                                   representation='tif',
                                   target='jpg',
                                   task='convert.tif_to_jpg')

            current_chain |= _link('list_files',
                                   representation='tif',
                                   target='jpg_thumbnails',
                                   task='convert.scale_image',
                                   max_width=50,
                                   max_height=50)

            current_chain |= _link('generate_xml',
                                   template_file='omp_template.xml',
                                   target_filename='omp_import.xml')

            current_chain |= _link('generate_xml',
                                    template_file='mets_template_monography.xml',
                                    target_filename='mets.xml',
                                    schema_file='mets.xsd')

            current_chain |= _link('publish_to_repository')

            current_chain |= _link('publish_to_archive')

            current_chain |= _link('publish_to_omp',
                                   omp_press_code=monograph_target['metadata']['press_code'])

            current_chain |= _link('cleanup_directories')

            current_chain |= _link(
                'finish_chain',
                success_msg="Monograph imported successfully",
                chain_input_directory=monograph_target['path'],
                user_name=user_name
            )
            chains.append(current_chain)

        return (chains, chain_parameters)


class NlpJob(BatchJob):
    job_type = 'nlp'
    label = 'Experimental NLP'
    description = "Experimental task to demonstrate the integration of natural language processing."

    def _create_chains(self, params, user_name):
        chains = []
        chain_parameters = []

        for target in params['targets']:
            for extension in params['options']['extensions']:
                if extension not in ['txt', 'pdf']:
                    raise Exception('Extension not supported: {}' + str(extension))

                chain_parameters.append(
                    target
                )

                task_params = dict(**target, **{'user': user_name})
                chain = _link('create_object', **task_params,
                                  initial_representation=extension)

                # "txt" and "pdf" start different chains
                # only pdfs get an intermediate conversion step
                if (extension == 'pdf'):
                    chain |= _link('list_files',
                                       representation='pdf',
                                       target='txt',
                                       task='convert.pdf_to_txt')

                    chain |= _link('nlp.annotate_pages',
                                        representation='txt',
                                        target='xmi.pages')

                    from_to = dict(representation='xmi.pages', target='xmi.pages.time')
                else:
                    from_to = dict(representation='txt', target='xmi.time')

                # both pdfs and txts are time tagged
                chain |= _link('list_files',
                                   **from_to,
                                   task='nlp_heideltime.time_annotate',
                                   lang=params['options']['lang'],
                                   document_creation_time=params['options']['document_creation_time'])

                # and finally tagged for other named entities
                last = from_to['target']
                next = last + '.entities'  # this is now e.g. "xmi.pages.time.entities"
                chain |= _link('list_files', representation=last, target=next, task='nlp.named_entities_annotate')

                # the pdf input also gets a final conversion to book viewer json
                if extension == 'pdf':
                    chain |= _link('list_files',
                                   representation='xmi.pages.time.entities',
                                   target='json',
                                   task='nlp.formats.dai_book_viewer_json')

                chains.append(chain)

        return (chains, chain_parameters)


def _link(name, **params):
    return celery_app.signature(name, kwargs=params)


def _generate_id():
    return str(uuid.uuid1())
