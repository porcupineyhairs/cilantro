from test.integration.job_type_test import JobTypeTest


class IngestBookTest(JobTypeTest):

    def test_success(self):
        self.stage_resource('objects', 'some_tiffs')

        data = self.post_job('ingest_book', {'paths': ['some_tiffs']})
        job_id = data['job_id']
        self.assertEqual('Accepted', data['status'])
        self.assert_job_successful(data['task_ids'])
        self.assert_file_in_repository(job_id, 'test.jpg')
        self.assert_file_in_repository(job_id, 'test.converted.pdf')
        self.assert_file_in_repository(job_id, 'merged.pdf')

        self.unstage_resource('some_tiffs')
        self.remove_object_from_repository(job_id)

    '''
    commented out until proper solution for
    http://dai-softsource.uni-koeln.de/issues/8297
    is found

    def test_error(self):
        self.stage_resource('objects', 'test_object')

        data = self.post_job('ingest_book', 'test_object')
        self.assertEqual('Accepted', data['status'])
        self.assert_status(data['job_id'], 'ERROR')

        self.unstage_resource('test_object')
    '''
