import os
import datetime

from pymongo import MongoClient, DESCENDING

client = MongoClient(os.environ['JOB_DB_URL'], int(os.environ['JOB_DB_PORT']))
db = client[os.environ['JOB_DB_NAME']]


def create_index():
    """
    Create index for faster lookup in database.

    The 2 fields that are used for lookup/update are indexed.
    """
    db.jobs.create_index([("job_id", DESCENDING),
                          ("user", DESCENDING)])


def get_jobs_for_user(user):
    """
    Find all jobs of the passed user in the job database.

    :param str user: username to find jobs belonging to
    :return: list of job objects
    """
    job_list = []
    for job in db.jobs.find({"user": user}, {'_id': False}):
        job_list.append(job)
    return job_list


def get_job_by_id(job_id):
    """
    Find job with the given job_id.

    :param str job_id: job-id to be queried
    :return: job object
    """
    job = db.jobs.find_one({"job_id": job_id}, {'_id': False})
    return job


def add_job(job_id, user, job_type, task_ids, job_params):
    """
    Add a job to the job database.

    :param str job_id: Cilantro-ID of the job
    :param str user: username which started the job
    :param str job_type: type of job, i.e. 'ingest_journal'
    :param list task_ids: Cilantro-IDs of all tasks belonging to that job
    :param dict job_params: Original paramters given when the job was created
    :return: None
    """
    timestamp = datetime.datetime.now()
    job = {'job_id': job_id,
           'user': user,
           'job_type': job_type,
           'name': _generate_job_name(job_type, job_params),
           'task_ids': task_ids,
           'state': 'new',
           'created': timestamp,
           'updated': timestamp,
           'params': job_params,
           'errors': []
           }

    db.jobs.insert_one(job)


def update_job(job_id, state, error=None):
    """
    Update a job to the job database with new state and updated timestamp.

    If there is an error object passed then that is added to the list
    of errors of that task. The errors are a list to  make it
    possible to keep executing the task chain even though some tasks
    throw errors. The errors are put into the job entry in the database
    and can be collected later.

    :param str job_id: Cilantro-ID of the job
    :param str state: new state of the job
    :param dict error: (optional) dict containig task name and error message
    :return: None
    """
    timestamp = datetime.datetime.now()
    db.jobs.update_many({"job_id": job_id},
                        {'$set': {'state': state, 'updated': timestamp}})
    if error:
        db.jobs.update_many({"job_id": job_id},
                            {'$push': {'errors': error}})


def _generate_job_name(job_type, job_params):
    """
    Generate job name based on job type and (first) file name.

    The job name is generated by appending the first file name of the
    files object if available. Otherwise the first file name of the
    first part is used.

    :param str job_type: type of the job
    :param list job_params: parameters of the job
    :return str: name of the job
    """
    if job_params['files']:
        first_file_name = job_params['files'][0]['file']
    else:
        first_file_name = job_params['parts'][0]['files'][0]['file']
    return f"JOB-{job_type}-{first_file_name}"
