import os

from utils.celery_client import celery_app
from workers.base_task import FileTask
from workers.default.image.image_scaling import scale_image


class ScaleImageTask(FileTask):
    """
    Creates copies of image files with new proportions while keeping ratio.

    TaskParams:
    -str image_max_width: width of the generated image file
    -str image_max_height: height of the generated image file

    Preconditions:
    - image files existing in format JPEG or TIFF

    Creates:
    - scaled copies of images
    """

    name = "image.scaling"

    def process_file(self, file, target_dir):
        """Read parameters and call the actual function."""
        new_width = int(self.get_param('image_max_width'))
        new_height = int(self.get_param('image_max_height'))

        file_name = os.path.splitext(os.path.basename(file))[0]
        file_extension = os.path.splitext(os.path.basename(file))[1]
        new_file_name = file_name +\
            "_" + str(new_width) +\
            "_" + str(new_height) +\
            "." + file_extension

        scale_image(file, new_width, new_height,
                    os.path.join(target_dir, new_file_name))


ScaleImageTask = celery_app.register_task(ScaleImageTask())
