import os
import pytest
import yaml

from tests import AsyncMock
from asyncio import Future

from app.utility.file_decryptor import decrypt


@pytest.mark.usefixtures(
    'init_base_world'
)
class TestFileService:

    @pytest.fixture
    def text_file(self, tmpdir):
        txt_str = 'Hello world!'
        f = tmpdir.mkdir('txt').join('test.txt')
        f.write(txt_str)
        assert f.read() == txt_str
        yield f

    def test_save_file(self, loop, file_svc, tmp_path):
        filename = "test_file.txt"
        payload = b'These are the file contents.'
        # Save temporary test file
        loop.run_until_complete(file_svc.save_file(filename, payload, tmp_path, encrypt=False))
        file_location = tmp_path / filename
        # Read file contents from saved file
        file_contents = open(file_location, "r")
        assert os.path.isfile(file_location)
        assert payload.decode("utf-8") == file_contents.read()

    def test_create_exfil_sub_directory(self, loop, file_svc):
        exfil_dir_name = 'unit-testing-Rocks'
        new_dir = loop.run_until_complete(file_svc.create_exfil_sub_directory(exfil_dir_name))
        assert os.path.isdir(new_dir)
        os.rmdir(new_dir)

    def test_read_write_result_file(self, tmpdir, file_svc):
        link_id = '12345'
        output = 'output testing unit'
        # write output data
        file_svc.write_result_file(link_id=link_id, output=output, location=tmpdir)

        # read output data
        output_data = file_svc.read_result_file(link_id=link_id, location=tmpdir)
        assert output_data == output

    def test_pack_file(self, loop, mocker, tmpdir, file_svc, data_svc):
        payload = 'unittestpayload'
        payload_content = b'content'
        new_payload_content = b'new_content'
        packer_name = 'test'

        # create temp files
        file = tmpdir.join(payload)
        file.write(payload_content)

        # start mocking up methods
        packer = mocker.Mock(return_value=Future())
        packer.return_value = packer
        packer.pack = AsyncMock(return_value=(payload, new_payload_content))
        data_svc.locate = AsyncMock(return_value=[])
        module = mocker.Mock()
        module.Packer = packer
        file_svc.packers[packer_name] = module
        file_svc.data_svc = data_svc
        file_svc.read_file = AsyncMock(return_value=(payload, payload_content))

        file_path, content, display_name = loop.run_until_complete(file_svc.get_file(headers=dict(file='%s:%s' % (packer_name, payload))))

        packer.pack.assert_called_once()
        assert payload == file_path
        assert content == new_payload_content

    def test_xored_filename_removal(self, loop, mocker, tmpdir, file_svc, data_svc):
        payload = 'unittestpayload.exe.xored'
        payload_content = b'content'
        new_payload_content = b'new_content'
        packer_name = 'test_xored_filename_removal'
        expected_display_name = 'unittestpayload.exe'

        # create temp files
        file = tmpdir.join(payload)
        file.write(payload_content)

        # start mocking up methods
        packer = mocker.Mock(return_value=Future())
        packer.return_value = packer
        packer.pack = AsyncMock(return_value=(payload, new_payload_content))
        data_svc.locate = AsyncMock(return_value=[])
        module = mocker.Mock()
        module.Packer = packer
        file_svc.packers[packer_name] = module
        file_svc.data_svc = data_svc
        file_svc.read_file = AsyncMock(return_value=(payload, payload_content))

        file_path, content, display_name = loop.run_until_complete(file_svc.get_file(headers=dict(file='%s:%s' % (packer_name, payload))))

        packer.pack.assert_called_once()
        assert payload == file_path
        assert content == new_payload_content
        assert display_name == expected_display_name

    def test_upload_file(self, loop, file_svc):
        upload_dir = loop.run_until_complete(file_svc.create_exfil_sub_directory('test-upload'))
        upload_filename = 'uploadedfile.txt'
        upload_content = b'this is a test upload file'
        loop.run_until_complete(file_svc.save_file(upload_filename, upload_content, upload_dir, encrypt=False))
        uploaded_file_path = os.path.join(upload_dir, upload_filename)
        assert os.path.isfile(uploaded_file_path)
        with open(uploaded_file_path, 'rb') as file:
            written_data = file.read()
        assert written_data == upload_content
        os.remove(uploaded_file_path)
        os.rmdir(upload_dir)

    def test_encrypt_upload(self, loop, file_svc):
        upload_dir = loop.run_until_complete(file_svc.create_exfil_sub_directory('test-encrypted-upload'))
        upload_filename = 'encryptedupload.txt'
        upload_content = b'this is a test upload file'
        loop.run_until_complete(file_svc.save_file(upload_filename, upload_content, upload_dir))
        uploaded_file_path = os.path.join(upload_dir, upload_filename)
        decrypted_file_path = upload_filename + '_decrypted'
        config_to_use = 'conf/default.yml'
        with open(config_to_use, encoding='utf-8') as conf:
            config = list(yaml.load_all(conf, Loader=yaml.FullLoader))[0]
        decrypt(uploaded_file_path, config, output_file=decrypted_file_path)
        assert os.path.isfile(decrypted_file_path)
        with open(decrypted_file_path, 'rb') as decrypted_file:
            decrypted_data = decrypted_file.read()
        assert decrypted_data == upload_content
        os.remove(uploaded_file_path)
        os.remove(decrypted_file_path)
        os.rmdir(upload_dir)

    def test_walk_file_path_exists_nonxor(self, loop, text_file, file_svc):
        ret = loop.run_until_complete(file_svc.walk_file_path(text_file.dirname, text_file.basename))
        assert ret == text_file

    def test_walk_file_path_notexists(self, loop, text_file, file_svc):
        ret = loop.run_until_complete(file_svc.walk_file_path(text_file.dirname, 'not-a-real.file'))
        assert ret is None

    def test_walk_file_path_xor_fn(self, loop, tmpdir, file_svc):
        f = tmpdir.mkdir('txt').join('xorfile.txt.xored')
        f.write("test")
        ret = loop.run_until_complete(file_svc.walk_file_path(f.dirname, 'xorfile.txt'))
        assert ret == f

    def test_remove_xored_extension(self, file_svc):
        test_value = 'example_file.exe.xored'
        expected_value = 'example_file.exe'
        ret = file_svc.remove_xored_extension(test_value)
        assert ret == expected_value

    def test_remove_xored_extension_to_non_xored_file(self, file_svc):
        test_value = 'example_file.exe'
        expected_value = 'example_file.exe'
        ret = file_svc.remove_xored_extension(test_value)
        assert ret == expected_value

    def test_add_xored_extension(self, file_svc):
        test_value = 'example_file.exe'
        expected_value = 'example_file.exe.xored'
        ret = file_svc.add_xored_extension(test_value)
        assert ret == expected_value

    def test_add_xored_extension_to_xored_file(self, file_svc):
        test_value = 'example_file.exe.xored'
        expected_value = 'example_file.exe.xored'
        ret = file_svc.add_xored_extension(test_value)
        assert ret == expected_value

    def test_is_extension_xored_true(self, file_svc):
        test_value = 'example_file.exe.xored'
        ret = file_svc.is_extension_xored(test_value)
        assert ret is True

    def test_is_extension_xored_false(self, file_svc):
        test_value = 'example_file.exe'
        ret = file_svc.is_extension_xored(test_value)
        assert ret is False
