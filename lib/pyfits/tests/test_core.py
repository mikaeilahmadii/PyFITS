from __future__ import division  # confidence high
from __future__ import with_statement

import gzip
import os
import warnings
import zipfile

import numpy as np

import pyfits as fits
from pyfits.convenience import _getext
from pyfits.util import BytesIO
from pyfits.tests import PyfitsTestCase
from pyfits.tests.util import catch_warnings, ignore_warnings, CaptureStdio

from nose.tools import assert_raises


class TestCore(PyfitsTestCase):
    def test_with_statement(self):
        with fits.open(self.data('ascii.fits')) as f:
            pass

    def test_missing_file(self):
        assert_raises(IOError, fits.open, self.temp('does-not-exist.fits'))

    def test_naxisj_check(self):
        hdulist = fits.open(self.data('o4sp040b0_raw.fits'))

        hdulist[1].header['NAXIS3'] = 500

        assert 'NAXIS3' in hdulist[1].header
        hdulist.verify('silentfix')
        assert 'NAXIS3' not in hdulist[1].header

    def test_byteswap(self):
        p = fits.PrimaryHDU()
        l = fits.HDUList()

        n = np.zeros(3, dtype='i2')
        n[0] = 1
        n[1] = 60000
        n[2] = 2

        c = fits.Column(name='foo', format='i2', bscale=1, bzero=32768,
                        array=n)
        t = fits.new_table([c])

        l.append(p)
        l.append(t)

        l.writeto(self.temp('test.fits'), clobber=True)

        with fits.open(self.temp('test.fits')) as p:
            assert p[1].data[1]['foo'] == 60000.0

    def test_add_del_columns(self):
        p = fits.ColDefs([])
        p.add_col(fits.Column(name='FOO', format='3J'))
        p.add_col(fits.Column(name='BAR', format='1I'))
        assert p.names == ['FOO', 'BAR']
        p.del_col('FOO')
        assert p.names == ['BAR']

    def test_add_del_columns2(self):
        hdulist = fits.open(self.data('tb.fits'))
        table = hdulist[1]
        assert table.data.dtype.names == ('c1', 'c2', 'c3', 'c4')
        assert table.columns.names == ['c1', 'c2', 'c3', 'c4']
        table.columns.del_col('c1')
        assert table.data.dtype.names == ('c2', 'c3', 'c4')
        assert table.columns.names == ['c2', 'c3', 'c4']

        table.columns.del_col('c3')
        assert table.data.dtype.names == ('c2', 'c4')
        assert table.columns.names == ['c2', 'c4']

        table.columns.add_col(fits.Column('foo', '3J'))
        assert table.data.dtype.names == ('c2', 'c4', 'foo')
        assert table.columns.names == ['c2', 'c4', 'foo']

        hdulist.writeto(self.temp('test.fits'), clobber=True)
        with fits.open(self.temp('test.fits')) as hdulist:
            table = hdulist[1]
            assert table.data.dtype.names == ('c1', 'c2', 'c3')
            assert table.columns.names == ['c1', 'c2', 'c3']

    def test_update_header_card(self):
        """A very basic test for the Header.update method--I'd like to add a
        few more cases to this at some point.
        """

        header = fits.Header()
        comment = 'number of bits per data pixel'
        header['BITPIX'] = (16, comment)
        assert 'BITPIX' in header
        assert header['BITPIX'] == 16
        assert header.ascard['BITPIX'].comment == comment

        # The new API doesn't support savecomment so leave this line here; at
        # any rate good to have testing of the new API mixed with the old API
        header.update('BITPIX', 32, savecomment=True)
        # Make sure the value has been updated, but the comment was preserved
        assert header['BITPIX'] == 32
        assert header.ascard['BITPIX'].comment == comment

        # The comment should still be preserved--savecomment only takes effect if
        # a new comment is also specified
        header['BITPIX'] = 16
        assert header.ascard['BITPIX'].comment == comment
        header.update('BITPIX', 16, 'foobarbaz', savecomment=True)
        assert header.ascard['BITPIX'].comment == comment

    def test_set_card_value(self):
        """Similar to test_update_header_card(), but tests the the
        `header['FOO'] = 'bar'` method of updating card values.
        """

        header = fits.Header()
        comment = 'number of bits per data pixel'
        card = fits.Card.fromstring('BITPIX  = 32 / %s' % comment)
        header.ascard.append(card)

        header['BITPIX'] = 32

        assert 'BITPIX' in header
        assert header['BITPIX'] == 32
        assert header.ascard['BITPIX'].key == 'BITPIX'
        assert header.ascard['BITPIX'].value == 32
        assert header.ascard['BITPIX'].comment == comment

    def test_uint(self):
        hdulist_f = fits.open(self.data('o4sp040b0_raw.fits'))
        hdulist_i = fits.open(self.data('o4sp040b0_raw.fits'), uint=True)

        assert hdulist_f[1].data.dtype == np.float32
        assert hdulist_i[1].data.dtype == np.uint16
        assert np.all(hdulist_f[1].data == hdulist_i[1].data)

    def test_fix_missing_card_append(self):
        hdu = fits.ImageHDU()
        errs = hdu.req_cards('TESTKW', None, None, 'foo', 'silentfix', [])
        assert len(errs) == 1
        assert 'TESTKW' in hdu.header
        assert hdu.header['TESTKW'] == 'foo'
        assert hdu.header.ascard[-1].key == 'TESTKW'

    def test_fix_invalid_keyword_value(self):
        hdu = fits.ImageHDU()
        hdu.header['TESTKW'] = 'foo'
        errs = hdu.req_cards('TESTKW', None,
                             lambda v: v == 'foo', 'foo', 'ignore', [])
        assert len(errs) == 0

        # Now try a test that will fail, and ensure that an error will be
        # raised in 'exception' mode
        errs = hdu.req_cards('TESTKW', None, lambda v: v == 'bar', 'bar',
                             'exception', [])
        assert len(errs) == 1
        assert errs[0] == "'TESTKW' card has invalid value 'foo'."

        # See if fixing will work
        hdu.req_cards('TESTKW', None, lambda v: v == 'bar', 'bar', 'silentfix',
                      [])
        assert hdu.header['TESTKW'] == 'bar'

    def test_unfixable_missing_card(self):
        class TestHDU(fits.hdu.base.NonstandardExtHDU):
            def _verify(self, option='warn'):
                errs = super(TestHDU, self)._verify(option)
                hdu.req_cards('TESTKW', None, None, None, 'fix', errs)
                return errs

        hdu = TestHDU(header=fits.Header())
        assert_raises(fits.VerifyError, hdu.verify, 'fix')

    def test_exception_on_verification_error(self):
        hdu = fits.ImageHDU()
        del hdu.header['XTENSION']
        assert_raises(fits.VerifyError, hdu.verify, 'exception')

    def test_ignore_verification_error(self):
        hdu = fits.ImageHDU()
        # The default here would be to issue a warning; ensure that no warnings
        # or exceptions are raised
        with catch_warnings():
            warnings.simplefilter('error')
            del hdu.header['NAXIS']
            try:
                hdu.verify('ignore')
            except Exception, e:
                self.fail('An exception occurred when the verification error '
                          'should have been ignored: %s' % e)
        # Make sure the error wasn't fixed either, silently or otherwise
        assert 'NAXIS' not in hdu.header

    def test_unrecognized_verify_option(self):
        hdu = fits.ImageHDU()
        assert_raises(ValueError, hdu.verify, 'foobarbaz')

    def test_getext(self):
        """
        Test the various different ways of specifying an extension header in
        the convenience functions.
        """

        hl, ext = _getext(self.data('test0.fits'), 'readonly', 1)
        assert ext == 1
        assert_raises(ValueError, _getext, self.data('test0.fits'), 'readonly',
                      1, 2)
        assert_raises(ValueError, _getext, self.data('test0.fits'), 'readonly',
                      (1, 2))
        assert_raises(ValueError, _getext, self.data('test0.fits'), 'readonly',
                      'sci', 'sci')
        assert_raises(TypeError, _getext, self.data('test0.fits'), 'readonly',
                      1, 2, 3)
        hl, ext = _getext(self.data('test0.fits'), 'readonly', ext=1)
        assert ext == 1
        hl, ext = _getext(self.data('test0.fits'), 'readonly', ext=('sci', 2))
        assert ext == ('sci', 2)
        assert_raises(TypeError, _getext, self.data('test0.fits'), 'readonly',
                      1, ext=('sci', 2), extver=3)
        assert_raises(TypeError, _getext, self.data('test0.fits'), 'readonly',
                      ext=('sci', 2), extver=3)

        hl, ext = _getext(self.data('test0.fits'), 'readonly', 'sci')
        assert ext == ('sci', 1)
        hl, ext = _getext(self.data('test0.fits'), 'readonly', 'sci', 1)
        assert ext == ('sci', 1)
        hl, ext = _getext(self.data('test0.fits'), 'readonly', ('sci', 1))
        assert ext == ('sci', 1)
        hl, ext = _getext(self.data('test0.fits'), 'readonly', 'sci',
                          extver=1, do_not_scale_image_data=True)
        assert ext == ('sci', 1)
        assert_raises(TypeError, _getext, self.data('test0.fits'), 'readonly',
                      'sci', ext=1)
        assert_raises(TypeError, _getext, self.data('test0.fits'), 'readonly',
                      'sci', 1, extver=2)

        hl, ext = _getext(self.data('test0.fits'), 'readonly', extname='sci')
        assert ext == ('sci', 1)
        hl, ext = _getext(self.data('test0.fits'), 'readonly', extname='sci',
                          extver=1)
        assert ext == ('sci', 1)
        assert_raises(TypeError, _getext, self.data('test0.fits'), 'readonly',
                      extver=1)

    def test_extension_name_case_sensitive(self):
        """
        Tests that setting fits.EXTENSION_NAME_CASE_SENSITIVE at runtime
        works.
        """

        if 'PYFITS_EXTENSION_NAME_CASE_SENSITIVE' in os.environ:
            del os.environ['PYFITS_EXTENSION_NAME_CASE_SENSITIVE']

        hdu = fits.ImageHDU()
        hdu.name = 'sCi'
        assert hdu.name == 'SCI'
        assert hdu.header['EXTNAME'] == 'SCI'

        try:
            fits.EXTENSION_NAME_CASE_SENSITIVE = True
            hdu = fits.ImageHDU()
            hdu.name = 'sCi'
            assert hdu.name == 'sCi'
            assert hdu.header['EXTNAME'] == 'sCi'
        finally:
            fits.EXTENSION_NAME_CASE_SENSITIVE = False

        hdu.name = 'sCi'
        assert hdu.name == 'SCI'
        assert hdu.header['EXTNAME'] == 'SCI'

    def test_hdu_fromstring(self):
        """
        Tests creating a fully-formed HDU object from a string containing the
        bytes of the HDU.
        """

        dat = open(self.data('test0.fits'), 'rb').read()

        offset = 0
        with fits.open(self.data('test0.fits')) as hdul:
            hdulen = hdul[0]._data_offset + hdul[0]._data_size
            hdu = fits.PrimaryHDU.fromstring(dat[:hdulen])
            assert isinstance(hdu, fits.PrimaryHDU)
            assert hdul[0].header == hdu.header
            assert hdu.data is None

        hdu.header['TEST'] = 'TEST'
        hdu.writeto(self.temp('test.fits'))
        with fits.open(self.temp('test.fits')) as hdul:
            assert isinstance(hdu, fits.PrimaryHDU)
            assert hdul[0].header[:-1] == hdu.header[:-1]
            assert hdul[0].header['TEST'] == 'TEST'
            assert hdu.data is None

        with fits.open(self.data('test0.fits'))as hdul:
            for ext_hdu in hdul[1:]:
                offset += hdulen
                hdulen = len(str(ext_hdu.header)) + ext_hdu._data_size
                hdu = fits.ImageHDU.fromstring(dat[offset:offset + hdulen])
                assert isinstance(hdu, fits.ImageHDU)
                assert ext_hdu.header == hdu.header
                assert (ext_hdu.data == hdu.data).all()

    def test_nonstandard_hdu(self):
        """
        Regression test for https://trac.assembla.com/pyfits/ticket/157

        Tests that "Nonstandard" HDUs with SIMPLE = F are read and written
        without prepending a superfluous and unwanted standard primary HDU.
        """

        data = np.arange(100, dtype=np.uint8)
        hdu = fits.PrimaryHDU(data=data)
        hdu.header['SIMPLE'] = False
        hdu.writeto(self.temp('test.fits'))

        info = [(0, '', 'NonstandardHDU', 5, (), '', '')]
        with fits.open(self.temp('test.fits')) as hdul:
            assert hdul.info(output=False) == info
            # NonstandardHDUs just treat the data as an unspecified array of
            # bytes.  The first 100 bytes should match the original data we
            # passed in...the rest should be zeros padding out the rest of the
            # FITS block
            assert (hdul[0].data[:100] == data).all()
            assert (hdul[0].data[100:] == 0).all()

    def test_extname(self):
        """Test getting/setting the EXTNAME of an HDU."""

        h1 = fits.PrimaryHDU()
        assert h1.name == 'PRIMARY'
        # Normally a PRIMARY HDU should not have an EXTNAME, though it should
        # have a default .name attribute
        assert 'EXTNAME' not in h1.header

        # The current version of the FITS standard does allow PRIMARY HDUs to
        # have an EXTNAME, however.
        h1.name = 'NOTREAL'
        assert h1.name == 'NOTREAL'
        assert h1.header.get('EXTNAME') == 'NOTREAL'

        # Updating the EXTNAME in the header should update the .name
        h1.header['EXTNAME'] = 'TOOREAL'
        assert h1.name == 'TOOREAL'

        # If we delete an EXTNAME keyword from a PRIMARY HDU it should go back
        # to the default
        del h1.header['EXTNAME']
        assert h1.name == 'PRIMARY'

        # For extension HDUs the situation is a bit simpler:
        h2 = fits.ImageHDU()
        assert h2.name == ''
        assert 'EXTNAME' not in h2.header
        h2.name = 'HELLO'
        assert h2.name == 'HELLO'
        assert h2.header.get('EXTNAME') == 'HELLO'
        h2.header['EXTNAME'] = 'GOODBYE'
        assert h2.name == 'GOODBYE'

    def test_extver_extlevel(self):
        """Test getting/setting the EXTVER and EXTLEVEL of and HDU."""

        # EXTVER and EXTNAME work exactly the same; their semantics are, for
        # now, to be inferred by the user.  Although they should never be less
        # than 1, the standard does not explicitly forbid any value so long as
        # it's an integer
        h1 = fits.PrimaryHDU()
        assert h1.ver == 1
        assert h1.level == 1
        assert 'EXTVER' not in h1.header
        assert 'EXTLEVEL' not in h1.header

        h1.ver = 2
        assert h1.header.get('EXTVER') == 2
        h1.header['EXTVER'] = 3
        assert h1.ver == 3
        del h1.header['EXTVER']
        h1.ver == 1

        h1.level = 2
        assert h1.header.get('EXTLEVEL') == 2
        h1.header['EXTLEVEL'] = 3
        assert h1.level == 3
        del h1.header['EXTLEVEL']
        assert h1.level == 1

        assert_raises(TypeError, setattr, h1, 'ver', 'FOO')
        assert_raises(TypeError, setattr, h1, 'level', 'BAR')


class TestConvenienceFunctions(PyfitsTestCase):
    def test_writeto(self):
        """
        Simple test for writing a trivial header and some data to a file
        with the `writeto()` convenience function.
        """

        data = np.zeros((100, 100))
        header = fits.Header()
        fits.writeto(self.temp('array.fits'), data, header=header,
                       clobber=True)
        hdul = fits.open(self.temp('array.fits'))
        assert len(hdul) == 1
        assert (data == hdul[0].data).all()

    def test_writeto_2(self):
        """
        Regression test for https://trac.assembla.com/pyfits/ticket/107

        Test of `writeto()` with a trivial header containing a single keyword.
        """

        data = np.zeros((100, 100))
        header = fits.Header()
        header.update('CRPIX1', 1.)
        fits.writeto(self.temp('array.fits'), data, header=header,
                       clobber=True, output_verify='silentfix')
        hdul = fits.open(self.temp('array.fits'))
        assert len(hdul) == 1
        assert (data == hdul[0].data).all()
        assert 'CRPIX1' in hdul[0].header
        assert hdul[0].header['CRPIX1'] == 1.0


class TestFileFunctions(PyfitsTestCase):
    """
    Tests various basic I/O operations, specifically in the pyfits.file._File
    class.
    """

    def test_open_nonexistent(self):
        """Test that trying to open a non-existent file results in an
        IOError (and not some other arbitrary exception).
        """

        try:
            fits.open(self.temp('foobar.fits'))
        except IOError, e:
            assert 'File does not exist' in str(e)
        except:
            raise

        # But opening in ostream or append mode should be okay, since they
        # allow writing new files
        for mode in ('ostream', 'append'):
            with fits.open(self.temp('foobar.fits'), mode=mode) as h:
                pass

            assert os.path.exists(self.temp('foobar.fits'))
            os.remove(self.temp('foobar.fits'))

    def test_open_gzipped(self):
        with ignore_warnings():
            assert len(fits.open(self._make_gzip_file())) == 5

    def test_detect_gzipped(self):
        """Test detection of a gzip file when the extension is not .gz."""

        with ignore_warnings():
            assert len(fits.open(self._make_gzip_file('test0.fz'))) == 5

    def test_writeto_append_mode_gzip(self):
        """Regression test for
        https://github.com/spacetelescope/PyFITS/issues/33

        Check that a new GzipFile opened in append mode can be used to write
        out a new FITS file.
        """

        # Note: when opening a GzipFile the 'b+' is superfluous, but this was
        # still how the original test case looked
        # Note: with statement not supported on GzipFile in older Python
        # versions
        fileobj =  gzip.GzipFile(self.temp('test.fits.gz'), 'ab+')
        h = fits.PrimaryHDU()
        try:
            h.writeto(fileobj)
        finally:
            fileobj.close()

        with fits.open(self.temp('test.fits.gz')) as hdul:
            assert hdul[0].header == h.header

    def test_open_zipped(self):
        zf = self._make_zip_file()

        with ignore_warnings():
            assert len(fits.open(self._make_zip_file())) == 5

        with ignore_warnings():
            assert len(fits.open(zipfile.ZipFile(zf))) == 5

    def test_detect_zipped(self):
        """Test detection of a zip file when the extension is not .zip."""

        zf = self._make_zip_file(filename='test0.fz')
        with ignore_warnings():
            assert len(fits.open(zf)) == 5

    def test_open_zipped_writeable(self):
        """Opening zipped files in a writeable mode should fail."""

        zf = self._make_zip_file()
        assert_raises(IOError, fits.open, zf, 'update')
        assert_raises(IOError, fits.open, zf, 'append')

        zf = zipfile.ZipFile(zf, 'a')
        assert_raises(IOError, fits.open, zf, 'update')
        assert_raises(IOError, fits.open, zf, 'append')

    def test_open_multiple_member_zipfile(self):
        """
        Opening zip files containing more than one member files should fail
        as there's no obvious way to specify which file is the FITS file to
        read.
        """

        zfile = zipfile.ZipFile(self.temp('test0.zip'), 'w')
        zfile.write(self.data('test0.fits'))
        zfile.writestr('foo', 'bar')
        zfile.close()

        assert_raises(IOError, fits.open, zfile.filename)

    def test_read_open_file(self):
        """Read from an existing file object."""

        with open(self.data('test0.fits'), 'rb') as f:
            assert len(fits.open(f)) == 5

    def test_read_closed_file(self):
        """Read from an existing file object that's been closed."""

        f = open(self.data('test0.fits'), 'rb')
        f.close()
        assert len(fits.open(f)) == 5

    def test_read_open_gzip_file(self):
        """Read from an open gzip file object."""

        gf = gzip.GzipFile(self._make_gzip_file())
        try:
            assert len(fits.open(gf)) == 5
        finally:
            gf.close()

    def test_open_gzip_file_for_writing(self):
        """Regression test for https://trac.assembla.com/pyfits/ticket/195."""

        gf = self._make_gzip_file()
        with fits.open(gf, mode='update') as h:
            h[0].header['EXPFLAG'] = 'ABNORMAL'
        with fits.open(gf) as h:
            # Just to make sur ethe update worked; if updates work
            # normal writes should work too...
            assert h[0].header['EXPFLAG'] == 'ABNORMAL'

    def test_read_file_like_object(self):
        """Test reading a FITS file from a file-like object."""

        filelike = BytesIO()
        with open(self.data('test0.fits'), 'rb') as f:
            filelike.write(f.read())
        filelike.seek(0)
        with ignore_warnings():
            assert len(fits.open(filelike)) == 5

    def test_updated_file_permissions(self):
        """
        Regression test for https://trac.assembla.com/pyfits/ticket/79

        Tests that when a FITS file is modified in update mode, the file
        permissions are preserved.
        """

        filename = self.temp('test.fits')
        hdul = [fits.PrimaryHDU(), fits.ImageHDU()]
        hdul = fits.HDUList(hdul)
        hdul.writeto(filename)

        old_mode = os.stat(filename).st_mode

        hdul = fits.open(filename, mode='update')
        hdul.insert(1, fits.ImageHDU())
        hdul.flush()
        hdul.close()

        assert old_mode == os.stat(filename).st_mode

    def test_fileobj_mode_guessing(self):
        """Tests whether a file opened without a specified pyfits mode
        ('readonly', etc.) is opened in a mode appropriate for the given file
        object.
        """

        self.copy_file('test0.fits')

        # Opening in text mode should outright fail
        for mode in ('r', 'w', 'a'):
            with open(self.temp('test0.fits'), mode) as f:
                assert_raises(ValueError, fits.HDUList.fromfile, f)

        # Need to re-copy the file since opening it in 'w' mode blew it away
        self.copy_file('test0.fits')

        with open(self.temp('test0.fits'), 'rb') as f:
            with fits.HDUList.fromfile(f) as h:
                assert h.fileinfo(0)['filemode'] == 'readonly'

        for mode in ('wb', 'ab'):
            with open(self.temp('test0.fits'), mode) as f:
                with fits.HDUList.fromfile(f) as h:
                    # Basically opening empty files for output streaming
                    assert len(h) == 0

        # Need to re-copy the file since opening it in 'w' mode blew it away
        self.copy_file('test0.fits')

        with open(self.temp('test0.fits'), 'wb+') as f:
            with fits.HDUList.fromfile(f) as h:
                # wb+ still causes an existing file to be overwritten so there
                # are no HDUs
                assert len(h) == 0

        # Need to re-copy the file since opening it in 'w' mode blew it away
        self.copy_file('test0.fits')

        with open(self.temp('test0.fits'), 'rb+') as f:
            with fits.HDUList.fromfile(f) as h:
                assert h.fileinfo(0)['filemode'] == 'update'

        with open(self.temp('test0.fits'), 'ab+') as f:
            with fits.HDUList.fromfile(f) as h:
                assert h.fileinfo(0)['filemode'] == 'append'

    def _make_gzip_file(self, filename='test0.fits.gz'):
        gzfile = self.temp(filename)
        with open(self.data('test0.fits'), 'rb') as f:
            gz = gzip.open(gzfile, 'wb')
            gz.write(f.read())
            gz.close()

        return gzfile

    def _make_zip_file(self, mode='copyonwrite', filename='test0.fits.zip'):
        zfile = zipfile.ZipFile(self.temp(filename), 'w')
        zfile.write(self.data('test0.fits'))
        zfile.close()

        return zfile.filename


class TestStreamingFunctions(PyfitsTestCase):
    """Test functionality of the StreamingHDU class."""

    def test_streaming_hdu(self):
        shdu = self._make_streaming_hdu(self.temp('new.fits'))
        assert isinstance(shdu.size, int)
        assert shdu.size == 100

    def test_streaming_hdu_file_wrong_mode(self):
        """
        Test that streaming an HDU to a file opened in the wrong mode fails as
        expected (any writeable mode is acceptable; any read-only mode should
        fail).
        """

        # touch new.fits
        with open(self.temp('new.fits'), 'wb'):
            pass

        with open(self.temp('new.fits'), 'rb') as f:
            header = fits.Header()
            assert_raises(ValueError, fits.StreamingHDU, f, header)

    def test_streaming_hdu_write_file(self):
        """Test streaming an HDU to an open file object."""

        arr = np.zeros((5, 5), dtype=np.int32)
        with open(self.temp('new.fits'), 'ab+') as f:
            shdu = self._make_streaming_hdu(f)
            shdu.write(arr)
            assert shdu.writecomplete
            assert shdu.size == 100
        hdul = fits.open(self.temp('new.fits'))
        assert len(hdul) == 1
        assert (hdul[0].data == arr).all()

    def test_streaming_hdu_write_file_like(self):
        """Test streaming an HDU to an open file-like object."""

        arr = np.zeros((5, 5), dtype=np.int32)
        # The file-like object underlying a StreamingHDU must be in binary mode
        sf = BytesIO()
        shdu = self._make_streaming_hdu(sf)
        shdu.write(arr)
        assert shdu.writecomplete
        assert shdu.size == 100

        sf.seek(0)
        hdul = fits.open(sf)
        assert len(hdul) == 1
        assert (hdul[0].data == arr).all()

    def test_streaming_hdu_append_extension(self):
        arr = np.zeros((5, 5), dtype=np.int32)
        with open(self.temp('new.fits'), 'ab+') as f:
            shdu = self._make_streaming_hdu(f)
            shdu.write(arr)
        # Doing this again should update the file with an extension
        with open(self.temp('new.fits'), 'ab+') as f:
            shdu = self._make_streaming_hdu(f)
            shdu.write(arr)

    def test_fix_invalid_extname(self):
        phdu = fits.PrimaryHDU()
        ihdu = fits.ImageHDU()
        ihdu.header['EXTNAME'] = 12345678
        hdul = fits.HDUList([phdu, ihdu])

        assert_raises(fits.VerifyError, hdul.writeto, self.temp('temp.fits'),
                      output_verify='exception')
        with CaptureStdio():
            hdul.writeto(self.temp('temp.fits'), output_verify='fix')
        with fits.open(self.temp('temp.fits')):
            assert hdul[1].name == '12345678'
            assert hdul[1].header['EXTNAME'] == '12345678'

    def _make_streaming_hdu(self, fileobj):
        hd = fits.Header()
        hd['SIMPLE'] = (True, 'conforms to FITS standard')
        hd['BITPIX'] = (32, 'array data type')
        hd['NAXIS'] = (2, 'number of array dimensions')
        hd['NAXIS1'] = 5
        hd['NAXIS2'] = 5
        hd['EXTEND'] = True
        return fits.StreamingHDU(fileobj, hd)
