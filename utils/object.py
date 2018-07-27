import os
from datetime import datetime
from io import BytesIO
import json
from typing import List, Iterator, TextIO
from distutils.dir_util import copy_tree
from utils.serialization import SerializableClass


class PathDoesNotExist(Exception):
    pass


class PagesInfo(SerializableClass):
    """
    Printing and visualisation information for the document.
    """

    showndesc: str
    startPrint: str
    endPrint: str


class Actor(SerializableClass):
    """
    Personal and legal entities in cilantro metadata.
    """

    firstname: str
    lastname: str


class ObjectMetadata(SerializableClass):
    """
    Basic metadata that can be recorded for every cilantro object
    """

    id: str
    title: str
    abstract: str
    description: str
    type: str
    creator: Actor
    created: datetime

    pages: PagesInfo

    year: int
    number: str
    volume: str
    identification: str


class Object:
    """
    A cilantro object, i.e. a single work unit.

    A cilantro object is a folder that only contains the following files and
    subfolders:
    * a file `meta.json` that contains the metadata for this object
    * additional metadata files that describe the object in different formats
      (e.g. mets.xml, tei.xml, marc.xml, ...)
    * a folder `data` that contains representations of the complete object
      in different binary formats, one representation corresponds to a
      subfolder that can hold one or more files in the same format
    * a folder `parts` that contains any number of subfolders that follow the
      naming patterns `part_XXXX` which in turn are cilantro objects that
      conform to this definition

    This class offers a single interface to the underlying structure and
    simplifies the management of cilantro objects.
    """

    INITIAL_REPRESENTATION = "origin"

    path: str
    metadata: ObjectMetadata

    def __init__(self, path):
        """
        Create an empty cilantro object that lives in path or finds one.

        :param str path: the Path where the object lives.
        """
        self.path = path

        if not os.path.exists(self.path):
            os.makedirs(self.path)
        if os.path.exists(os.path.join(self.path, 'meta.json')):
            with open(os.path.join(self.path, 'meta.json'), 'r', encoding="utf-8") as data:

                try:
                    self.metadata = ObjectMetadata.from_dict(json.load(data))
                except ValueError:
                    self.metadata = ObjectMetadata()
        else:
            open(os.path.join(self.path, 'meta.json'), 'a', encoding="utf-8").close()
            self.metadata = ObjectMetadata()

    def write(self):
        """
        Write the current object metadata state to the file system.

        :return: None
        """
        with open(os.path.join(self.path, 'meta.json'), 'w', encoding="utf-8") as stream:
            stream.write(self.metadata.to_json())

    def add_stream(self, file_name: str, representation: str, file: BytesIO):
        """
        Add a stream to a representation of the object.

        A new representation is created if it does not already exist.

        :param str file_name: how the generated file should be named
        :param str representation: The file format of the input.
        :param BytesIO file: The input stream
        :return: None
        """
        if not os.path.exists(self.get_representation_dir(representation)):
            os.makedirs(self.get_representation_dir(representation))
        with open(os.path.join(self.get_representation_dir(representation), file_name), 'wb+') as stream:
            stream.write(file.read())

    def add_file(self, representation: str, src: str):
        """
        Add a file to a representation of the object.

        This acts as a convenience wrapper around `add_stream()` and handles
        opening and reading the file.

        The generated file has the same name as the source file.

        :param str representation: The file format of the input.
        :param str src: The path to the source file
        :return: None
        """
        with open(src, 'rb') as stream:
            self.add_stream(os.path.basename(src), representation,
                            BytesIO(stream.read()))

    def add_files(self, representation: str, files: str):
        """
        Add a list of files to a representation of the object.

        :param str representation: The file format of the input.
        :param list[str] files: The paths to the source files
        :return: None
        """
        for file in files:
            self.add_file(representation, file)

    def list_representations(self) -> List[str]:
        """
        List the representations that the object offers.

        :return List[str]:
        """
        representations = []
        if os.path.exists(self._get_data_dir()):
            representations = os.listdir(self._get_data_dir())
            representations.sort()
        return representations

    def get_representation(self, representation: str) -> Iterator[BytesIO]:
        """
        Get all files that correspond to a given representation.

        :param str representation:
        :return Iterator[BytesIO]:
        """
        representations = []
        path = self.get_representation_dir(representation)
        for filename in os.listdir(path):
            if not os.path.isdir(os.path.join(path, filename)):
                with open(os.path.join(path, filename), 'rb') as file:
                    representations.append(BytesIO(file.read()))
        return iter(representations)

    def write_metadata_file(self, name: str, read_stream: TextIO):
        """
        Add a metadata file to the object.

        A new file is created with the given name if it does not already exist,
        otherwise the existing file is overwritten.

        :param read_stream:
        :param name: the filename to be written in
        """
        with open(os.path.join(self.path, name), 'w+') as file:
            file.write(read_stream.read())

    def set_metadata_from_dict(self, d):
        self.metadata = ObjectMetadata.from_dict(d)
        self.write()

    def add_child(self):
        """
        Add a sub-object to this object.

        Creates a new part_XXXX folder under parts. Also creates the parts
        folder if it does not exist already.

        :return: Object
        """
        if not os.path.exists(self._get_part_dir()):
            os.makedirs(self._get_part_dir())
            return Object(os.path.join(self._get_part_dir(), 'part_0001'))

        return Object(os.path.join(self._get_part_dir(),
                                   _get_part_dir_for_index(len(os.listdir(self._get_part_dir())) + 1)))

    def get_child(self, index: int):
        part_name = _get_part_dir_for_index(index)
        path = os.path.join(self._get_part_dir(), part_name)
        return Object(path)

    def get_children(self):
        """
        Get all sub-objects of this object

        :return Iterator[Object]:
        """
        sub_objects = []
        if os.path.isdir(self._get_part_dir()):
            for d in [d for d in os.listdir(self._get_part_dir()) if
                      os.path.isdir(os.path.join(self._get_part_dir(), d))]:
                if _is_part_dir_format(d):
                    sub_objects.append(Object(os.path.join(self._get_part_dir(), d)))
        sub_objects.sort(key=lambda obj: obj.path)
        return iter(sub_objects)

    def copy(self, path):
        """
        Copy the whole contents of this object to a new location.

        :param str path: The new location on the file system
        :return Object: A new object instance representing the copy
        """
        copy_tree(self.path, path)

    def _get_part_dir(self):
        return os.path.join(self.path, 'parts')

    def _get_data_dir(self):
        return os.path.join(self.path, 'data')

    def get_representation_dir(self, representation: str):
        return os.path.join(self._get_data_dir(), representation)


def _is_part_dir_format(dir_name):
    return 'part_' in dir_name


def _get_part_dir_for_index(index: int):
    part_name = f"part_{str(index).zfill(4)}"
    return part_name
