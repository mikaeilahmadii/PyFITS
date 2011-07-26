from __future__ import division # confidence high
from __future__ import with_statement

import gzip

import numpy as np

import pyfits
from pyfits.tests import PyfitsTestCase

from nose.tools import assert_equal


class TestCore(PyfitsTestCase):
    def test_with_statement(self):
        with pyfits.open(self.data('ascii.fits')) as f:
            pass

    def test_open_gzipped(self):
        gzfile = self.temp('test0.fits.gz')
        with open(self.data('test0.fits'), 'rb') as f:
            gz = gzip.open(gzfile, 'wb')
            gz.write(f.read())
            gz.close()

        hdul = pyfits.open(gzfile)
        assert_equal(len(hdul), 5)

    def test_naxisj_check(self):
        hdulist = pyfits.open(self.data('o4sp040b0_raw.fits'))

        hdulist[1].header.update("NAXIS3", 500)

        assert 'NAXIS3' in hdulist[1].header
        hdulist.verify('fix')
        assert 'NAXIS3' not in hdulist[1].header

    def test_byteswap(self):
        p = pyfits.PrimaryHDU()
        l = pyfits.HDUList()

        n = np.zeros(3, dtype='i2')
        n[0] = 1
        n[1] = 60000
        n[2] = 2

        c = pyfits.Column(name='foo', format='i2', bscale=1, bzero=32768,
                          array=n)
        t = pyfits.new_table([c])

        l.append(p)
        l.append(t)

        l.writeto(self.temp('test.fits'), clobber=True)

        p = pyfits.open(self.temp('test.fits'))
        assert_equal(p[1].data[1]['foo'], 60000.0)

    def test_add_del_columns(self):
        p = pyfits.ColDefs([])
        p.add_col(pyfits.Column(name='FOO', format='3J'))
        p.add_col(pyfits.Column(name='BAR', format='1I'))
        assert_equal(p.names, ['FOO', 'BAR'])
        p.del_col('FOO')
        assert_equal(p.names, ['BAR'])

    def test_add_del_columns2(self):
        hdulist = pyfits.open(self.data('tb.fits'))
        table = hdulist[1]
        assert_equal(table.data.dtype.names, ('c1', 'c2', 'c3', 'c4'))
        assert_equal(table.columns.names, ['c1', 'c2', 'c3', 'c4'])
        #old_data = table.data.base.copy().view(pyfits.FITS_rec)
        table.columns.del_col('c1')
        assert_equal(table.data.dtype.names, ('c2', 'c3', 'c4'))
        assert_equal(table.columns.names, ['c2', 'c3', 'c4'])

        #for idx in range(len(old_data)):
        #    assert_equal(np.all(old_data[idx][1:], table.data[idx]))

        table.columns.del_col('c3')
        assert_equal(table.data.dtype.names, ('c2', 'c4'))
        assert_equal(table.columns.names, ['c2', 'c4'])

        #for idx in range(len(old_data)):
        #    assert_equal(np.all(old_data[idx][2:], table.data[idx]))

        table.columns.add_col(pyfits.Column('foo', '3J'))
        assert_equal(table.data.dtype.names, ('c2', 'c4', 'foo'))
        assert_equal(table.columns.names, ['c2', 'c4', 'foo'])

        hdulist.writeto(self.temp('test.fits'), clobber=True)
        hdulist = pyfits.open(self.temp('test.fits'))
        table = hdulist[1]
        assert_equal(table.data.dtype.names, ('c1', 'c2', 'c3'))
        assert_equal(table.columns.names, ['c1', 'c2', 'c3'])

    def test_update_header_card(self):
        """A very basic test for the Header.update method--I'd like to add a
        few more cases to this at some point.
        """

        header = pyfits.Header()
        comment = 'number of bits per data pixel'
        header.update('BITPIX', 16, comment)
        assert 'BITPIX' in header
        assert_equal(header['BITPIX'], 16)
        assert_equal(header.ascard['BITPIX'].comment, comment)

        header.update('BITPIX', 32, savecomment=True)
        # Make sure the value has been updated, but the comment was preserved
        assert_equal(header['BITPIX'], 32)
        assert_equal(header.ascard['BITPIX'].comment, comment)

        # The comment should still be preserved--savecomment only takes effect if
        # a new comment is also specified
        header.update('BITPIX', 16)
        assert_equal(header.ascard['BITPIX'].comment, comment)
        header.update('BITPIX', 16, 'foobarbaz', savecomment=True)
        assert_equal(header.ascard['BITPIX'].comment, comment)

    def test_set_card_value(self):
        """Similar to test_update_header_card(), but tests the the
        `header['FOO'] = 'bar'` method of updating card values.
        """

        header = pyfits.Header()
        comment = 'number of bits per data pixel'
        card = pyfits.Card.fromstring('BITPIX  = 32 / %s' % comment)
        header.ascard.append(card)

        header['BITPIX'] = 32

        assert 'BITPIX' in header
        assert_equal(header['BITPIX'], 32)
        assert_equal(header.ascard['BITPIX'].key, 'BITPIX')
        assert_equal(header.ascard['BITPIX'].value, 32)
        assert_equal(header.ascard['BITPIX'].comment, comment)

    def test_uint(self):
        hdulist_f = pyfits.open(self.data('o4sp040b0_raw.fits'))
        hdulist_i = pyfits.open(self.data('o4sp040b0_raw.fits'), uint=True)

        assert_equal(hdulist_f[1].data.dtype, np.float32)
        assert_equal(hdulist_i[1].data.dtype, np.uint16)
        assert np.all(hdulist_f[1].data == hdulist_i[1].data)

    def test_fix_missing_card_append(self):
        hdu = pyfits.ImageHDU()
        errs = hdu.req_cards('TESTKW', None, None, 'foo', 'silentfix', [])
        assert_equal(len(errs), 1)
        assert 'TESTKW' in hdu.header
        assert_equal(hdu.header['TESTKW'], 'foo')
        assert_equal(hdu.header.ascard[-1].key, 'TESTKW')

    def test_fix_invalid_keyword_value(self):
        hdu = pyfits.ImageHDU()
        hdu.header.update('TESTKW', 'foo')
        errs = hdu.req_cards('TESTKW', None,
                             lambda v: v == 'foo', 'foo', 'ignore', [])
        assert_equal(len(errs), 0)

        # Now try a test that will fail, and ensure that an error will be
        # raised in 'exception' mode
        errs = hdu.req_cards('TESTKW', None, lambda v: v == 'bar', 'bar',
                             'exception', [])
        assert_equal(len(errs), 1)
        assert_equal(errs[0], "'TESTKW' card has invalid value 'foo'.")

        # See if fixing will work
        hdu.req_cards('TESTKW', None, lambda v: v == 'bar', 'bar', 'silentfix',
                      [])
        assert_equal(hdu.header['TESTKW'], 'bar')