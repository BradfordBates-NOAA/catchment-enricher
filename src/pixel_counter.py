'''Created on 02/21/2022.
Written by:
Anuska Narayanan (The University of Alabama Department of Geography, anarayanan1@crimson.ua.edu;
Sophie Williams (The University of Alabama Department of Geography, scwilliams8@crimson.ua.edu; and
Brad Bates (NOAA, Lynker, and the National Water Center, bradford.bates@noaa.gov

Derived from a Python version of a zonal statistics function writted by Matthew Perry (@perrygeo).

Description: This script isolates the number of pixels per class of a raster within the outlines of
one or more polygons and displays them in a table. It accomplishes this by rasterizing the vector file,
masking out the desired areas of both rasters, and then summarizing them in a dataframe. It makes use
of the gdal, numpy, and pandas function libraries.
Inputs: one raster file with at least one set of attributes; one vector file containing one or more polygon
boundaries
Output: a dataframe table with rows displayed by each polygon within the vector file, and columns
displaying the pixel count of each raster attribute class in the polygon
'''

# Import raster and vector function libraries
from osgeo import gdal, ogr
from osgeo.gdalconst import *
# Import numerical data library
import numpy as np
# Import file management library
import sys
# Import data analysis library
import pandas as pd
import argparse
from pandas import DataFrame

# Set up error handler
gdal.PushErrorHandler('CPLQuietErrorHandler')


# Function that transforms vector dataset to raster
def bbox_to_pixel_offsets(gt, bbox):
    originX = gt[0]
    originY = gt[3]
    pixel_width = gt[1]
    pixel_height = gt[5]
    x1 = int((bbox[0] - originX) / pixel_width)
    x2 = int((bbox[1] - originX) / pixel_width) + 1

    y1 = int((bbox[3] - originY) / pixel_height)
    y2 = int((bbox[2] - originY) / pixel_height) + 1

    xsize = x2 - x1
    ysize = y2 - y1
    return (x1, y1, xsize, ysize)


# Main function that determines zonal statistics of raster classes in a polygon area
def zonal_stats(vector_path, raster_path, nodata_value=None, global_src_extent=False):
    # Opens raster file and sets path
    rds = gdal.Open(raster_path, GA_ReadOnly)
    assert rds
    rb = rds.GetRasterBand(1)
    rgt = rds.GetGeoTransform()

    if nodata_value:
        nodata_value = float(nodata_value)
        rb.SetNoDataValue(nodata_value)
    # Opens vector file and sets path
    vds = ogr.Open(vector_path)
    vlyr = vds.GetLayer(0)

    # Creates an in-memory numpy array of the source raster data covering the whole extent of the vector layer
    if global_src_extent:
        # use global source extent
        # useful only when disk IO or raster scanning inefficiencies are your limiting factor
        # advantage: reads raster data in one pass
        # disadvantage: large vector extents may have big memory requirements
        src_offset = bbox_to_pixel_offsets(rgt, vlyr.GetExtent())
        src_array = rb.ReadAsArray(*src_offset)

        # calculate new geotransform of the layer subset
        new_gt = (
            (rgt[0] + (src_offset[0] * rgt[1])),
            rgt[1],
            0.0,
            (rgt[3] + (src_offset[1] * rgt[5])),
            0.0,
            rgt[5]
        )

    mem_drv = ogr.GetDriverByName('Memory')
    driver = gdal.GetDriverByName('MEM')

    # Loop through vectors, as many as exist in file
    # Creates new list to contain their stats
    stats = []
    feat = vlyr.GetNextFeature()
    while feat is not None:

        if not global_src_extent:
            # use local source extent
            # fastest option when you have fast disks and well indexed raster (ie tiled Geotiff)
            # advantage: each feature uses the smallest raster chunk
            # disadvantage: lots of reads on the source raster
            src_offset = bbox_to_pixel_offsets(rgt, feat.geometry().GetEnvelope())
            src_array = rb.ReadAsArray(*src_offset)

            # calculate new geotransform of the feature subset
            new_gt = (
                (rgt[0] + (src_offset[0] * rgt[1])),
                rgt[1],
                0.0,
                (rgt[3] + (src_offset[1] * rgt[5])),
                0.0,
                rgt[5]
            )

        # Create a temporary vector layer in memory
        mem_ds = mem_drv.CreateDataSource('out')
        mem_layer = mem_ds.CreateLayer('poly', None, ogr.wkbPolygon)
        mem_layer.CreateFeature(feat.Clone())

        # Rasterize temporary vector layer
        rvds = driver.Create('', src_offset[2], src_offset[3], 1, gdal.GDT_Byte)
        rvds.SetGeoTransform(new_gt)
        gdal.RasterizeLayer(rvds, [1], mem_layer, burn_values=[1])
        rv_array = rvds.ReadAsArray()

        # Mask the source data array with our current feature and get statistics (pixel count) of masked areas
        # we take the logical_not to flip 0<->1 to get the correct mask effect
        # we also mask out nodata values explictly
        masked = np.ma.MaskedArray(
            src_array,
            mask=np.logical_or(
                src_array == nodata_value,
                np.logical_not(rv_array)
            )
        )
        # Acquires information for table on each raster attribute per poly feature
        feature_stats = {
            'FID': int(feat.GetFID()),
            'HydroID': feat.GetField('HydroID'),
            'TotalPixels': int(masked.count()),
            '11': np.count_nonzero((masked == [11])),
            '12': np.count_nonzero((masked == [12])),
            '21': np.count_nonzero((masked == [21])),
            '22': np.count_nonzero((masked == [22])),
            '23': np.count_nonzero((masked == [23])),
            '24': np.count_nonzero((masked == [24])),
            '31': np.count_nonzero((masked == [31])),
            '41': np.count_nonzero((masked == [41])),
            '42': np.count_nonzero((masked == [42])),
            '43': np.count_nonzero((masked == [43])),
            '51': np.count_nonzero((masked == [51])),
            '52': np.count_nonzero((masked == [52])),
            '71': np.count_nonzero((masked == [71])),
            '72': np.count_nonzero((masked == [72])),
            '73': np.count_nonzero((masked == [73])),
            '74': np.count_nonzero((masked == [74])),
            '81': np.count_nonzero((masked == [81])),
            '82': np.count_nonzero((masked == [82])),
            '90': np.count_nonzero((masked == [90])),
            '95': np.count_nonzero((masked == [95])),
        }
        stats.append(feature_stats)

        rvds = None
        mem_ds = None
        feat = vlyr.GetNextFeature()

    vds = None
    rds = None
    return stats


# Creates and prints dataframe containing desired statistics
if __name__ == "__main__":
    #opts = {'VECTOR': sys.argv[1:], 'RASTER': sys.argv[2:]}
    #stats = zonal_stats(opts['VECTOR'], opts['RASTER'])

    parser = argparse.ArgumentParser(description='Computes pixel counts for raster classes within a vector area.')
    parser.add_argument('-v', '--vector',
                        help='Path to vector file.',
                        required=True)
    parser.add_argument('-r', '--raster',
                        help='Path to raster file.',
                        required=True)
    parser.add_argument('-c', '--csv',
                        help='Path to export csv file.',
                        required=True)
    # Assign variables from arguments.
    args = vars(parser.parse_args())
    vector = args['vector']
    raster = args['raster']
    export = args['csv']
    stats = zonal_stats(vector,raster)


    # Export CSV
    df = pd.DataFrame(stats)
    print(df)
    df.to_csv(export, sep='\t', index=False)
