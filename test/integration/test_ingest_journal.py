from test.integration.job_type_test import JobTypeTest


class IngestJournalTest(JobTypeTest):

    def test_success(self):
        self.stage_resource('objects', 'a_journal')

        params = self.load_params_from_file('params', 'a_journal.json')
        data, status_code = self.post_job('ingest_journal', params)

        self.assertEquals(status_code, 200)
        job_id = data['job_id']
        self.assertEqual('Accepted', data['status'])
        self.assert_status(job_id, 'SUCCESS')

        files_generated = [
            'e2e-testing.pdf.0.pdf',
            'e2e-testing.pdf.1.pdf',
            'data.json'
        ]
        for file in files_generated:
            self.assert_file_in_repository(job_id, file)
        self.unstage_resource('pdf')
        self.remove_object_from_repository(job_id)
