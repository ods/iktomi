import unittest, os, tempfile, shutil
import gc
from sqlalchemy import Column, Integer, VARBINARY, orm, create_engine
from sqlalchemy.schema import MetaData
from sqlalchemy.ext.declarative import declarative_base
from iktomi.db.sqla.declarative import AutoTableNameMeta
from iktomi.db.files import TransientFile, PersistentFile, \
                                     FileManager
import iktomi.db.sqla.files
from iktomi.db.sqla.files import FileProperty, filesessionmaker


Base = declarative_base(metaclass=AutoTableNameMeta)

CustomBase = declarative_base(metaclass=AutoTableNameMeta)

try:
    from unittest import mock
except:
    import mock


class ObjWithFile(Base):

    id = Column(Integer, primary_key=True)
    file_name = Column(VARBINARY(250))
    file_size = Column(Integer)
    file = FileProperty(file_name,
                        name_template='obj/{random}',
                        cache_properties={'size': 'file_size'})
    file_by_id_name = Column(VARBINARY(250))
    file_by_id = FileProperty(file_by_id_name, name_template='obj/{item.id}')

    something = Column(Integer, default=0)


class ModelLevelObj(CustomBase):

    id = Column(Integer, primary_key=True)
    file_name = Column(VARBINARY(250))
    file = FileProperty(file_name, name_template='obj/{random}')


class MetadataLevelObj(CustomBase):

    id = Column(Integer, primary_key=True)
    file_name = Column(VARBINARY(250))
    file = FileProperty(file_name, name_template='obj/{random}')


class Subclass(ObjWithFile):

    __tablename__ = None


class SqlaFilesTests(unittest.TestCase):

    Model = ObjWithFile

    def setUp(self):

        self.transient_root = tempfile.mkdtemp()
        self.persistent_root = tempfile.mkdtemp()
        self.transient_url = '/transient/'
        self.persistent_url = '/media/'

        self.file_manager = FileManager(self.transient_root,
                                        self.persistent_root,
                                        self.transient_url,
                                        self.persistent_url)

        self.metadata_transient_root = tempfile.mkdtemp()
        self.metadata_persistent_root = tempfile.mkdtemp()
        self.metadata_transient_url = '/metadata/transient/'
        self.metadata_persistent_url = '/metadata/media/'

        self.metadata_file_manager = FileManager(self.metadata_transient_root,
                                                 self.metadata_persistent_root,
                                                 self.metadata_transient_url,
                                                 self.metadata_persistent_url)

        self.model_transient_root = tempfile.mkdtemp()
        self.model_persistent_root = tempfile.mkdtemp()
        self.model_transient_url = '/model/transient/'
        self.model_persistent_url = '/model/media/'

        self.model_file_manager = FileManager(self.model_transient_root,
                                              self.model_persistent_root,
                                              self.model_transient_url,
                                              self.model_persistent_url)


        Session = filesessionmaker(orm.sessionmaker(), self.file_manager,
            file_managers={
                MetadataLevelObj.metadata: self.metadata_file_manager,
                ModelLevelObj: self.model_file_manager,
            })

        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        CustomBase.metadata.create_all(engine)
        self.db = Session(bind=engine)

    def tearDown(self):
        shutil.rmtree(self.transient_root)
        shutil.rmtree(self.persistent_root)
        shutil.rmtree(self.metadata_transient_root)
        shutil.rmtree(self.metadata_persistent_root)
        shutil.rmtree(self.model_transient_root)
        shutil.rmtree(self.model_persistent_root)

    def test_session(self):
        self.assertTrue(hasattr(self.db, 'file_manager'))
        self.assertIsInstance(self.db.file_manager, FileManager)

    def test_find_file_manager(self):
        self.assertTrue(hasattr(self.db, 'find_file_manager'))

        self.assertEqual(self.db.find_file_manager(self.Model.file),
                         self.file_manager)

        self.assertEqual(self.db.find_file_manager(ModelLevelObj.file),
                         self.model_file_manager)

        self.assertEqual(self.db.find_file_manager(MetadataLevelObj.file),
                         self.metadata_file_manager)

    def test_create(self):
        obj = self.Model()

        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test')
        self.assertIsInstance(obj.file, TransientFile)
        self.assertIsNotNone(obj.file_name)
        self.db.add(obj)
        self.db.commit()
        self.assertIsInstance(obj.file, PersistentFile)
        self.assertFalse(os.path.exists(f.path))
        self.assertTrue(os.path.isfile(obj.file.path))
        self.assertEqual(open(obj.file.path).read(), 'test')

    def test_create_metadata_obj(self):
        metadata_obj = MetadataLevelObj()
        metadata_filemanager = self.db.find_file_manager(metadata_obj)
        metadata_file = metadata_filemanager.new_transient()
        with open(metadata_file.path, 'wb') as fp:
            fp.write(b'test')
        metadata_obj.file = metadata_file

        self.assertTrue(metadata_obj.file.path.startswith(self.metadata_transient_root))

        self.db.add(metadata_obj)
        self.db.commit()

        self.assertTrue(metadata_obj.file.path.startswith(self.metadata_persistent_root))

    def test_create_model_obj(self):
        model_obj = ModelLevelObj()
        model_filemanager = self.db.find_file_manager(model_obj)
        model_file = model_filemanager.new_transient()
        with open(model_file.path, 'wb') as fp:
            fp.write(b'test')
        model_obj.file = model_file

        self.assertTrue(model_obj.file.path.startswith(self.model_transient_root))

        self.db.add(model_obj)
        self.db.commit()

        self.assertTrue(model_obj.file.path.startswith(self.model_persistent_root))

    def test_update_none2file(self):
        obj = self.Model()
        self.db.add(obj)
        self.db.commit()

        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test')
        self.assertIsInstance(obj.file, TransientFile)
        self.assertIsNotNone(obj.file_name)
        self.db.commit()

        # cleanup self.Model.file._states.items() to get the result
        # from scratch, not from cache
        obj_id = obj.id
        obj = None
        gc.collect()
        obj = self.db.query(self.Model).get(obj_id)

        self.assertIsInstance(obj.file, PersistentFile)
        self.assertFalse(os.path.exists(f.path))
        self.assertTrue(os.path.isfile(obj.file.path))
        self.assertEqual(open(obj.file.path).read(), 'test')
        self.assertEqual(obj.file.size, 4)
        self.assertEqual(obj.file_size, 4)

    def test_update_file2none(self):
        obj = self.Model()
        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test')
        self.db.add(obj)
        self.db.commit()

        pf = obj.file

        obj.file = None
        self.assertIsNone(obj.file_name)
        self.assertTrue(os.path.exists(pf.path))
        self.assertEqual(obj.file_size, 4)
        self.db.commit()

        self.assertFalse(os.path.exists(pf.path))
        self.assertEqual(obj.file_size, None)

    def test_update_file2file(self):
        obj = self.Model()
        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test1')
        self.db.add(obj)
        self.db.commit()
        pf1 = obj.file

        self.assertEqual(obj.file_size, 5)

        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test22')
        self.assertIsInstance(obj.file, TransientFile)
        self.assertIsNotNone(obj.file_name)
        self.db.commit()

        self.assertIsInstance(obj.file, PersistentFile)
        self.assertFalse(os.path.exists(f.path))
        self.assertFalse(os.path.exists(pf1.path))
        self.assertTrue(os.path.isfile(obj.file.path))
        self.assertEqual(open(obj.file.path).read(), 'test22')
        self.assertEqual(obj.file_size, 6)

    def test_update_file2self(self):
        obj = self.Model()
        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test1')
        self.db.add(obj)
        self.db.commit()
        pf1 = obj.file

        obj.file = self.file_manager.get_persistent(obj.file.name)
        self.db.commit()

        self.assertIsInstance(obj.file, PersistentFile)
        self.assertTrue(os.path.exists(obj.file.path))
        self.assertEqual(pf1.path, obj.file.path)

        # XXX for test coverage
        #     have no idea what extra check can be performed
        obj.file = obj.file
        self.assertTrue(os.path.exists(obj.file.path))
        self.assertEqual(pf1.path, obj.file.path)

    @unittest.expectedFailure
    def test_update_file2file_not_random(self):
        obj = self.Model()

        obj.file_by_id = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test1')
        self.db.add(obj)
        self.db.commit()
        self.assertEqual(obj.file_by_id_name,
                         self.Model.file_by_id.name_template.format(item=obj))
        pf1 = obj.file_by_id

        obj.file_by_id = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test2')
        self.assertIsInstance(obj.file_by_id, TransientFile)
        self.assertIsNotNone(obj.file_by_id_name)
        self.db.commit()

        self.assertIsInstance(obj.file_by_id, PersistentFile)
        self.assertFalse(os.path.exists(f.path))
        self.assertFalse(os.path.exists(pf1.path))
        self.assertTrue(os.path.isfile(obj.file_by_id.path))
        self.assertEqual(open(obj.file_by_id.path).read(), 'test2')

    @unittest.expectedFailure
    def test_update_random_collision(self):
        obj = self.Model()
        self.db.add(obj)
        self.db.commit()

        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test')

        persistent = self.file_manager.get_persistent(obj.file_name)
        dirname = os.path.dirname(persistent.path)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        with open(persistent.path, 'wb') as fp:
            fp.write(b'taken')

        self.assertIsInstance(obj.file, TransientFile)
        self.assertIsNotNone(obj.file_name)
        self.db.commit()
        self.assertIsInstance(obj.file, PersistentFile)
        self.assertFalse(os.path.exists(f.path))
        self.assertTrue(os.path.isfile(obj.file.path))
        self.assertEqual(open(obj.file.path).read(), 'test')
        self.assertNotEqual(persistent.path, obj.file.path)
        self.assertEqual(open(persistent.path).read(), 'taken')

    def test_update_none2persistent(self):
        f = self.file_manager.get_persistent('persistent.txt')
        with open(f.path, 'wb') as fp:
            fp.write(b'test1')

        obj = self.Model()
        obj.file = f
        self.db.add(obj)
        self.db.commit()

        self.assertIsInstance(obj.file, PersistentFile)
        self.assertTrue(os.path.exists(obj.file.path))
        self.assertEqual(obj.file.name, 'persistent.txt')

    def test_delete(self):
        obj = self.Model()
        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test')
        self.db.add(obj)
        self.db.commit()
        pf = obj.file
        self.db.delete(obj)
        self.db.commit()
        self.assertFalse(os.path.exists(pf.path))

    def test_set_invalid(self):
        obj = self.Model()
        self.assertRaises(ValueError, lambda: setattr(obj, 'file', 'test'))

    def test_cached_lost(self):
        obj = self.Model()
        self.db.add(obj)
        self.db.commit()
        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test')
        self.db.commit()

        os.unlink(obj.file.path)

        self.assertEqual(obj.file.size, 4)
        self.assertEqual(obj.file_size, 4)

        del obj.file.size
        self.assertEqual(obj.file.size, None)

    def test_file2none_lost(self):
        obj = self.Model()
        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test')
        self.db.add(obj)
        self.db.commit()

        os.unlink(obj.file.path)
        obj.file = None
        self.db.commit()

        self.assertEqual(obj.file_size, None)

    def test_file_manager_for_field(self):
        def make():
            file_manager = FileManager(self.transient_root,
                                       self.persistent_root,
                                       self.transient_url,
                                       self.persistent_url)
            filesessionmaker(orm.sessionmaker(), self.file_manager,
                file_managers={
                    ObjWithFile.file: file_manager,
                })

        self.assertRaises(NotImplementedError, make)

    def test_detached_object(self):
        obj = self.Model()
        self.db.add(obj)
        self.db.commit()
        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test')
        self.db.commit()
        # cleanup self.Model.file._states.items() to get the result
        # from scratch, not from cache
        obj_id = obj.id
        obj = None
        gc.collect()
        obj = self.db.query(self.Model).get(obj_id)

        with mock.patch.object(iktomi.db.sqla.files,
                               'object_session', return_value=None):
            with self.assertRaises(RuntimeError) as exc:
                obj.file
            self.assertEqual('Object is detached', str(exc.exception))

    def test_absent_file_manager(self):
        obj = self.Model()
        del self.db.file_manager
        self.db.add(obj)
        self.db.commit()
        obj.file = f = self.file_manager.new_transient()
        with open(f.path, 'wb') as fp:
            fp.write(b'test')
        self.db.commit()
        # cleanup self.Model.file._states.items() to get the result
        # from scratch, not from cache
        obj_id = obj.id
        obj = None
        gc.collect()
        obj = self.db.query(self.Model).get(obj_id)

        with self.assertRaises(RuntimeError) as exc:
            obj.file
        self.assertEqual("Session doesn't support file management", str(exc.exception))

class SqlaFilesTestsSubclass(SqlaFilesTests):

    Model = Subclass

