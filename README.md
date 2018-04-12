# Cilantro

Cilantro is a task runner designed to manage long running distributed jobs that
operate on file system objects. It is written in Python and uses
[Celery](http://docs.celeryproject.org/) and [Flask](http://flask.pocoo.org/).

## Running the app with docker

    docker-compose build
    docker-compose up

### Testing the application

In order for the test to function properly you have to create some files with
.tif ending in the folder `./data/repository/foo/upload`.

The web service runs on port 5000. The following command will create a test task:

    curl -XPOST http://localhost:5000/job/test/foo
    
You can then query the job status with the returned job_id:

    curl http://localhost:5000/job/<job_id>
    
### Monitoring

[Flower](https://flower.readthedocs.io/) is included in the docker config and
is available for debugging under http://localhost:5555.
