# Taken from http://matplotlib.org/examples/api/custom_projection_example.html
# and adapted to Albers Equal Area transform.
# CAUTION: This implementation does *not* work!
from __future__ import unicode_literals

import matplotlib
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle, Polygon
from matplotlib.path import Path
from matplotlib.collections import PolyCollection
from matplotlib.ticker import NullLocator, Formatter, FixedLocator
from matplotlib.transforms import Affine2D, BboxTransformTo, Transform, blended_transform_factory
from matplotlib.projections import register_projection
import matplotlib.spines as mspines
import matplotlib.axis as maxis

import numpy as np

# This example projection class is rather long, but it is designed to
# illustrate many features, not all of which will be used every time.
# It is also common to factor out a lot of these methods into common
# code used by a number of projections with similar characteristics
# (see geo.py).


class SkymapperAxes(Axes):
    """
    A base class for a Skymapper axes that takes in ra_0, dec_0, dec_1, dec_2.

    The base class takes care of clipping and interpolating with matplotlib.
    
    Subclass and override class method get_projection_class.

    """
    # The subclass projection must specify a name.  This will be used be the
    # user to select the projection.

    name = None

    @classmethod
    def get_projection_class(kls):
        raise NotImplementedError('Must implement this in subclass')

    def __init__(self, *args, **kwargs):
        self.dec_0 = kwargs.pop('dec_0', 0)
        self.dec_1 = kwargs.pop('dec_1', 0)
        self.dec_2 = kwargs.pop('dec_2', 60)
        self.ra_0 = kwargs.pop('ra_0', 0)

        Axes.__init__(self, *args, **kwargs)

        self.cla()

    def _init_axis(self):
        self.xaxis = maxis.XAxis(self)
        self.yaxis = maxis.YAxis(self)
        # FIXME: we probably want to register axis with spines.
        # Axes._init_axis() -- until HammerAxes.xaxis.cla() works.
        #self.spines['hammer'].register_axis(self.yaxis)
        self._update_transScale()

    def cla(self):
        """
        Override to set up some reasonable defaults.
        """
        # Don't forget to call the base class
        Axes.cla(self)

        # Set up a default grid spacing
        self.set_meridian_grid(30)
        self.set_parallel_grid(15)

        # Turn off minor ticking altogether
        self.xaxis.set_minor_locator(NullLocator())
        self.yaxis.set_minor_locator(NullLocator())

        # Do not display ticks -- we only want gridlines and text
        self.xaxis.set_ticks_position('none')
        self.yaxis.set_ticks_position('none')

        self.set_xlim(0, 360)
        self.set_ylim(-90, 90)
        self.set_autoscale_on(False)

    def _set_lim_and_transforms(self):
        """
        This is called once when the plot is created to set up all the
        transforms for the data, text and grids.
        """
        # There are three important coordinate spaces going on here:
        #
        #    1. Data space: The space of the data itself
        #
        #    2. Axes space: The unit rectangle (0, 0) to (1, 1)
        #       covering the entire plot area.
        #
        #    3. Display space: The coordinates of the resulting image,
        #       often in pixels or dpi/inch.

        # This function makes heavy use of the Transform classes in
        # ``lib/matplotlib/transforms.py.`` For more information, see
        # the inline documentation there.

        # The goal of the first two transformations is to get from the
        # data space (in this case meridian and parallel) to axes
        # space.  It is separated into a non-affine and affine part so
        # that the non-affine part does not have to be recomputed when
        # a simple affine change to the figure has been made (such as
        # resizing the window or changing the dpi).

        # 1) The core transformation from data space into
        # rectilinear space defined in the HammerTransform class.
        self.transProjection = self.get_projection_class()(ra_0=self.ra_0,
                        dec_0=self.dec_0, dec_1=self.dec_1, dec_2=self.dec_2)

        # 2) The above has an output range that is not in the unit
        # rectangle, so scale and translate it so it fits correctly
        # within the axes.  The peculiar calculations of xscale and
        # yscale are specific to a Aitoff-Hammer projection, so don't
        # worry about them too much.

        # This will be updated after the xy limits are set.
        self.transAffine = Affine2D()

        # 3) This is the transformation from axes space to display
        # space.
        self.transAxes = BboxTransformTo(self.bbox)

        # Now put these 3 transforms together -- from data all the way
        # to display coordinates.  Using the '+' operator, these
        # transforms will be applied "in order".  The transforms are
        # automatically simplified, if possible, by the underlying
        # transformation framework.
        self.transData = \
            self.transProjection + \
            self.transAffine + \
            self.transAxes

        self.transClip = \
            self.transProjection + \
            self.transAffine 

        # The main data transformation is set up.  Now deal with
        # gridlines and tick labels.

        # Longitude gridlines and ticklabels.  The input to these
        # transforms are in display space in x and axes space in y.
        # Therefore, the input values will be in range (-xmin, 0),
        # (xmax, 1).  The goal of these transforms is to go from that
        # space to display space.  The tick labels will be offset 4
        # pixels from the equator.
        self._xaxis_pretransform = \
            Affine2D() \
            .scale(1.0, 180) \
            .translate(0.0, -90)
        self._xaxis_transform = \
            self._xaxis_pretransform + \
            self.transData
        self._xaxis_text1_transform = \
            Affine2D().scale(1.0, 1.0) + \
            self.transData + \
            Affine2D().translate(0.0, -0.0)
        self._xaxis_text2_transform = \
            Affine2D().scale(1.0, 1.0) + \
            self.transData + \
            Affine2D().translate(0.0, 0.0)

        # Now set up the transforms for the parallel ticks.  The input to
        # these transforms are in axes space in x and display space in
        # y.  Therefore, the input values will be in range (0, -ymin),
        # (1, ymax).  The goal of these transforms is to go from that
        # space to display space.  The tick labels will be offset 4
        # pixels from the edge of the axes ellipse.
        self._yaxis_stretch = Affine2D().scale(360, 1.0).translate(0.0, 0.0)
        self._yaxis_transform = \
            self._yaxis_stretch + \
            self.transData
        yaxis_text_base = \
            self._yaxis_stretch + \
            self.transProjection + \
            (self.transAffine +
             self.transAxes)
        self._yaxis_text1_transform = \
            yaxis_text_base + \
            Affine2D().translate(8.0, 0.0)
        self._yaxis_text2_transform = \
            yaxis_text_base + \
            Affine2D().translate(-8.0, 0.0)

    def _update_affine(self):
        # update the transformations and clip paths
        # after new lims are set.
        self._yaxis_stretch\
            .clear() \
            .scale(self.viewLim.width, 1.0) \
            .translate(self.viewLim.x0, 0.0)
        self._xaxis_pretransform \
            .clear() \
            .scale(1.0, self.viewLim.height) \
            .translate(0.0, self.viewLim.y0)

        ra_0 = self.transProjection.ra_0


        corners_data = np.array([[self.viewLim.x0, self.viewLim.y0],
                      [ra_0,            self.viewLim.y0],
                      [self.viewLim.x1, self.viewLim.y0],
                      [self.viewLim.x1, self.viewLim.y1],
                      [self.viewLim.x0, self.viewLim.y1],])

        corners = self.transProjection.transform_non_affine(corners_data)

        x_0 = corners[0][0]
        x_1 = corners[2][0]

        # special case when x_1 is wrapped back to x_0
        # FIXME: I don't think we need it anymore.
        if x_0 == x_1: x_1 = - x_0

        y_0 = corners[1][1]
        y_1 = max([corners[3][1], corners[4][1]])

        xscale = np.abs(x_0 - x_1)
        yscale = np.abs(y_0 - y_1)

        self.transAffine.clear() \
            .scale(0.95 / xscale, 0.95 / yscale)  \
            .translate(0.5, 0.5)

        # now update the clipping path
        path = Path(corners_data)
        path = self.transClip.transform_path(path)
        self.patch.set_xy(path.vertices)

    def get_xaxis_transform(self, which='grid'):
        """
        Override this method to provide a transformation for the
        x-axis grid and ticks.
        """
        assert which in ['tick1', 'tick2', 'grid']
        return self._xaxis_transform

    def get_xaxis_text1_transform(self, pixelPad):
        """
        Override this method to provide a transformation for the
        x-axis tick labels.

        Returns a tuple of the form (transform, valign, halign)
        """
        return self._xaxis_text1_transform, 'bottom', 'center'

    def get_xaxis_text2_transform(self, pixelPad):
        """
        Override this method to provide a transformation for the
        secondary x-axis tick labels.

        Returns a tuple of the form (transform, valign, halign)
        """
        return self._xaxis_text2_transform, 'top', 'center'

    def get_yaxis_transform(self, which='grid'):
        """
        Override this method to provide a transformation for the
        y-axis grid and ticks.
        """
        assert which in ['tick1', 'tick2', 'grid']
        return self._yaxis_transform

    def get_yaxis_text1_transform(self, pixelPad):
        """
        Override this method to provide a transformation for the
        y-axis tick labels.

        Returns a tuple of the form (transform, valign, halign)
        """
        return self._yaxis_text1_transform, 'center', 'left'

    def get_yaxis_text2_transform(self, pixelPad):
        """
        Override this method to provide a transformation for the
        secondary y-axis tick labels.

        Returns a tuple of the form (transform, valign, halign)
        """
        return self._yaxis_text2_transform, 'center', 'right'

    def _gen_axes_patch(self):
        """
        ClipPath.

        Initially set to a size of 2 box in transAxes.

        After xlim and ylim are set, this will be changed to the actual
        region in transData.

        For unclear reason the very initial clip path is always applied
        to the grid. Therefore we set size to 2.0 to avoid bad clipping.
        """
        return Polygon([(0, 0), (2, 0), (2, 2), (0, 2)], fill=False)

    def _gen_axes_spines(self):
        d = {
            'left': mspines.Spine.linear_spine(self, spine_type='left'),
            'right': mspines.Spine.linear_spine(self, spine_type='right'),
            'top': mspines.Spine.linear_spine(self, spine_type='top'),
            'bottom': mspines.Spine.linear_spine(self, spine_type='bottom'),
        }
        d['left'].set_position(('axes', 0))
        d['right'].set_position(('axes', 1))
        d['top'].set_position(('axes', 0))
        d['bottom'].set_position(('axes', 1))
        #FIXME: these spines can be moved wit set_position(('axes', ?)) but
        # 'data' fails. Because the transformation is non-separatable,
        # and because spines / data makes that assumption, we probably
        # do not have a easy way to support moving spines via native matplotlib
        # api on data axis.

        # also the labels currently do not follow the spines. Likely because
        # they are not registered?

        return d

    # Prevent the user from applying scales to one or both of the
    # axes.  In this particular case, scaling the axes wouldn't make
    # sense, so we don't allow it.
    def set_xscale(self, *args, **kwargs):
        if args[0] != 'linear':
            raise NotImplementedError
        Axes.set_xscale(self, *args, **kwargs)

    def set_yscale(self, *args, **kwargs):
        if args[0] != 'linear':
            raise NotImplementedError
        Axes.set_yscale(self, *args, **kwargs)

    # when xlim and ylim are updated, the transformation
    # needs to be updated too.
    def set_xlim(self, *args, **kwargs):
        Axes.set_xlim(self, *args, **kwargs)

        # FIXME: wrap x0 x1 to ensure they enclose ra0.
        x0, x1 = self.viewLim.intervalx
        if not x0 < self.transProjection.ra_0 or \
           not x1 > self.transProjection.ra_0:
            raise ValueError("The given limit in RA does not enclose ra_0")
            
        self._update_affine()

    def set_ylim(self, *args, **kwargs):
        Axes.set_ylim(self, *args, **kwargs)
        self._update_affine()

    def histmap(self, ra, dec, nside=32, weights=None, mean=False, **kwargs):
        r = histogrammap(ra, dec, nside, weights)

        if weights is not None:
            w, N = r
        else:
            w = r
        if mean:
            mask = N != 0
            w[mask] /= N[mask]
        else:
            mask = w > 0

        return w, mask, self.mapshow(w, mask, nest=False, **kwargs)

    def mapshow(self, map, mask, nest=False, **kwargs):
        """ Display a healpix map """
        v = _boundary(mask, nest)
        coll = PolyCollection(v, array=map[mask], transform=self.transData, **kwargs)
        self.add_collection(coll)
        return coll

    def format_coord(self, lon, lat):
        """
        Override this method to change how the values are displayed in
        the status bar.

        In this case, we want them to be displayed in degrees N/S/E/W.
        """
        lon = lon
        lat = lat
        if lat >= 0.0:
            ns = 'N'
        else:
            ns = 'S'
        if lon >= 0.0:
            ew = 'E'
        else:
            ew = 'W'
        # \u00b0 : degree symbol
        return '%f\u00b0%s, %f\u00b0%s' % (abs(lat), ns, abs(lon), ew)

    class DegreeFormatter(Formatter):
        """
        This is a custom formatter that converts the native unit of
        radians into (truncated) degrees and adds a degree symbol.
        """

        def __init__(self, round_to=1.0):
            self._round_to = round_to

        def __call__(self, x, pos=None):
            degrees = round(x / self._round_to) * self._round_to
            # \u00b0 : degree symbol
            return "%d\u00b0" % degrees

    def set_meridian_grid(self, degrees):
        """
        Set the number of degrees between each meridian grid.

        It provides a more convenient interface to set the ticking than set_xticks would.
        """
        # Set up a FixedLocator at each of the points, evenly spaced
        # by degrees.
        x0, x1 = self.get_xlim()
        number = ((x1 - x0) / degrees) + 1
        self.xaxis.set_major_locator(
            FixedLocator(
                np.linspace(x0, x1, number, True)[1:-1]))
        # Set the formatter to display the tick labels in degrees,
        # rather than radians.
        self.xaxis.set_major_formatter(self.DegreeFormatter(degrees))

    def set_parallel_grid(self, degrees):
        """
        Set the number of degrees between each meridian grid.

        It provides a more convenient interface than set_yticks would.
        """
        # Set up a FixedLocator at each of the points, evenly spaced
        # by degrees.
        y0, y1 = self.get_ylim()
        number = ((y1 - y0) / degrees) + 1
        self.yaxis.set_major_locator(
            FixedLocator(
                np.linspace(y0, y1, number, True)[1:-1]))
        # Set the formatter to display the tick labels in degrees,
        # rather than radians.
        self.yaxis.set_major_formatter(self.DegreeFormatter(degrees))

    # Interactive panning and zooming is not supported with this projection,
    # so we override all of the following methods to disable it.
    def _in_axes(self, mouseevent):
        if hasattr(self._pan_trans): 
            return True
        else:
            return Axes._in_axes(self, mouseevent)

    def can_zoom(self):
        """
        Return True if this axes support the zoom box
        """
        return False

    def start_pan(self, x, y, button):
        self._pan_trans = self.transAxes.inverted() + \
                blended_transform_factory(
                        self._yaxis_stretch,
                        self._xaxis_pretransform,)

    def end_pan(self):
        delattr(self, '_pan_trans')

    def drag_pan(self, button, key, x, y):
        pan1 = self._pan_trans.transform([(x, y)])[0]
        self.transProjection.ra_0 = 360 - pan1[0]
        self.transProjection.dec_0 = pan1[1]
        self._update_affine()

# now define the Albers equal area axes

class AlbersEqualAreaAxes(SkymapperAxes):
    """
    A custom class for the Albers Equal Area projection.

    https://en.wikipedia.org/wiki/Albers_projection
    """

    name = 'aea'

    @classmethod
    def get_projection_class(kls):
        return kls.AlbersEqualAreaTransform

    # Now, the transforms themselves.
    class AlbersEqualAreaTransform(Transform):
        """
        The base Hammer transform.
        """
        input_dims = 2
        output_dims = 2
        is_separable = False

        def __init__(self, ra_0=0, dec_0=0, dec_1=0, dec_2=60, **kwargs):
            Transform.__init__(self, **kwargs)
            self.dec_0 = dec_0
            self.dec_1 = dec_1
            self.dec_2 = dec_2

            self.ra_0 = ra_0
            self.deg2rad = np.pi/180

            self.n = (np.sin(dec_1 * self.deg2rad) + np.sin(dec_2 * self.deg2rad)) / 2
            self.C = np.cos(dec_1 * self.deg2rad)**2 + 2 * self.n * np.sin(dec_1 * self.deg2rad)
            self.rho_0 = self.__rho__(dec_0)

        def __rho__(self, dec):
            return np.sqrt(self.C - 2 * self.n * np.sin(dec * self.deg2rad)) / self.n

        def transform_non_affine(self, ll):
            """
            Override the transform_non_affine method to implement the custom
            transform.

            The input and output are Nx2 numpy arrays.
            """
            ra = ll[:,0]
            dec = ll[:,1]

            ra_ = np.array([ra - self.ra_0]) * -1 # inverse for RA

            # FIXME: problem with the slices sphere: outer parallel needs to be dubplicated at the expense of the central one
            theta = self.n * ra_[0]
            rho = self.__rho__(dec)
            rt = np.array([
                rho*np.sin(theta * self.deg2rad),
                 self.rho_0 - rho*np.cos(theta * self.deg2rad)]).T
            if np.isnan(rt).any(): raise ValueError('abc')
            return rt

        # This is where things get interesting.  With this projection,
        # straight lines in data space become curves in display space.
        # This is done by interpolating new values between the input
        # values of the data.  Since ``transform`` must not return a
        # differently-sized array, any transform that requires
        # changing the length of the data array must happen within
        # ``transform_path``.
        def transform_path_non_affine(self, path):
            # Adaptive interpolation:
            # we keep adding control points, till all control points
            # have an error of less than 0.01 (about 1%)
            # or if the number of control points is > 80.
            path = path.cleaned(curves=False)
            v = path.vertices
            diff = v[:, 0] - v[0, 0]
            v00 = v[0][0] - self.ra_0 
            while v00 > 180: v00 -= 360
            while v00 < -180: v00 += 360
            v00 += self.ra_0
            v[:, 0] = v00 + diff

            isteps = path._interpolation_steps * 2
            while True:
                ipath = path.interpolated(isteps)
                tiv = self.transform(ipath.vertices)
                itv = Path(self.transform(path.vertices)).interpolated(isteps).vertices
                if np.mean(np.abs(tiv - itv)) < 0.01:
                    break
                if isteps > 80:
                    break
                isteps = isteps * 2

            return Path(tiv, ipath.codes)

        transform_path_non_affine.__doc__ = \
            Transform.transform_path_non_affine.__doc__

        if matplotlib.__version__ < '1.2':
            transform = transform_non_affine
            transform_path = transform_path_non_affine
            transform_path.__doc__ = Transform.transform_path.__doc__

        def inverted(self):
            return AlbersEqualAreaAxes.InvertedAlbersEqualAreaTransform(
                        ra_0=self.ra_0, dec_0=self.dec_0, dec_1=self.dec_1, dec_2=self.dec_2)
        inverted.__doc__ = Transform.inverted.__doc__

    class InvertedAlbersEqualAreaTransform(Transform):
        """ Inverted transform.

            This will always only give values in the prime ra0-180 ~ ra0+180 range, I believe.
            So it is inherently broken. I wonder when matplotlib actually calls this function,
            given that interactive is disabled.
        """
        input_dims = 2
        output_dims = 2
        is_separable = False

        def __init__(self, ra_0=0, dec_0=0, dec_1=-30, dec_2=30, **kwargs):
            Transform.__init__(self, **kwargs)
            self.dec_0 = dec_0
            self.dec_1 = dec_1
            self.ra_0 = ra_0
            self.deg2rad = np.pi/180

            self.n = (np.sin(dec_1 * self.deg2rad) + np.sin(dec_2 * self.deg2rad)) / 2
            self.C = np.cos(dec_1 * self.deg2rad)**2 + 2 * self.n * np.sin(dec_1 * self.deg2rad)
            self.rho_0 = self.__rho__(dec_0)

        def __rho__(self, dec):
            return np.sqrt(self.C - 2 * self.n * np.sin(dec * self.deg2rad)) / self.n

        def transform_non_affine(self, xy):
            x = xy[:,0]
            y = xy[:,1]

            rho = np.sqrt(x**2 + (self.rho_0 - y)**2)

            # make sure that the signs are correct
            if self.n >= 0:
                theta = np.arctan2(x, self.rho_0 - y) / self.deg2rad
            else:
                theta = np.arctan2(-x, -(self.rho_0 - y)) / self.deg2rad
            return np.array([self.ra_0 - theta/self.n,
                np.arcsin((self.C - (rho * self.n)**2)/(2*self.n)) / self.deg2rad]).T

            transform_non_affine.__doc__ = Transform.transform_non_affine.__doc__

        if matplotlib.__version__ < '1.2':
            transform = transform_non_affine

        def inverted(self):
            # The inverse of the inverse is the original transform... ;)
            return AlbersEqualAreaAxes.AlbersEqualAreaTransform(ra_0=self.ra_0, dec_0=self.dec_0, dec_1=self.dec_1, dec_2=self.dec_2)
        inverted.__doc__ = Transform.inverted.__doc__

# a few helper functions talking to healpy/healpix. 
def _boundary(mask, nest=False):
    """Generate healpix vertices for pixels where mask is True

    Requires: healpy

    Args:
        pix: list of pixel numbers
        nest: nested or not
        nside: HealPix nside

    Returns:
        vertices
        vertices: (N,4,2), RA/Dec coordinates of 4 boundary points of cell
    """
    import healpy as hp

    pix = mask.nonzero()[0]
    nside = hp.npix2nside(len(mask))
    # get the vertices that confine each pixel
    # convert to RA/Dec (thanks to Eric Huff)
    vertices = np.zeros((pix.size, 4, 2))
    for i in xrange(pix.size):
        corners = hp.vec2ang(np.transpose(hp.boundaries(nside,pix[i],nest=nest)))
        corners = np.degrees(corners) 

        # ensure no patch wraps around.
        diff = corners[1] - corners[1][0]
        diff[diff > 180] -= 360
        diff[diff < -180] += 360
        corners[1] = corners[1][0] + diff

        vertices[i,:,0] = corners[1]
        vertices[i,:,1] = 90.0 - corners[0]

    return vertices

def histogrammap(ra, dec, nside=32, weights=None):
    import healpy as hp 
    ipix = hp.ang2pix(nside, np.radians(90-dec), np.radians(ra), nest=False)
    npix = hp.nside2npix(nside)
    if weights is not None:
        w = np.bincount(ipix, weights=weights, minlength=npix)
        N = np.bincount(ipix, minlength=npix)
        return w, N
    else:
        w = 1.0 * np.bincount(ipix, minlength=npix)
        return w

# Now register the projection with matplotlib so the user can select
# it.
register_projection(AlbersEqualAreaAxes)

if __name__ == '__main__':
    import matplotlib.pyplot as plt
    # Now make a simple example using the custom projection.

    import numpy as np
    import aea_projection
    fig = plt.figure(figsize=(6, 6))

    ra = np.random.uniform(size=10000, low=0, high=360)
    dec = np.random.uniform(size=10000, low=-90, high=90)

    ax = fig.add_subplot(111, aspect='equal', projection="aea", dec_1=-20., dec_2=30., ra_0=180, dec_0=0.)
    ax.set_meridian_grid(30)
    ax.set_parallel_grid(30)
    #ax.set_xlim(0, 360)
    #ax.set_ylim(-70, 70)
    ax.plot(ra, dec, '.')
    ax.grid()
    plt.savefig('xxx.png')
