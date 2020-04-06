import sys; sys.path.append('..'); sys.path.append('../lib/')
from lib.raster_io import raster_to_array, array_to_raster
from lib.raster_resample import resample
from lib.stats_filters import mode_filter, feather_s2_filter, mean_filter, median_filter
from lib.stats_local_no_kernel import radiometric_quality, radiometric_quality_spatial, radiometric_quality_haze, radiometric_change_mask
from lib.stats_kernel import create_kernel
from lib.utils_core import weighted_quantile, madstd
from time import time
import cv2
import os
import xml.etree.ElementTree as ET
import datetime
import math
from glob import glob
import numpy as np

# SCL
##  0: SC_NODATA
##  1: SC_SATURATED_DEFECTIVE
##  2: SC_DARK_FEATURE_SHADOW
##  3: SC_CLOUD_SHADOW
##  4: SC_VEGETATION
##  5: SC_NOT_VEGETATED
##  6: SC_WATER
##  7: SC_UNCLASSIFIED
##  8: SC_CLOUD_MEDIUM_PROBA
##  9: SC_CLOUD_HIGH_PROBA
## 10: SC_THIN_CIRRUS
## 11: SC_SNOW_ICE

def get_band_paths(safe_folder):
    bands = {
        "10m": {
          "B02": None,
          "B03": None,
          "B04": None,
          "B08": None,
        },
        "20m": {
          "B02": None,
          "B03": None,
          "B04": None,
          "B05": None,
          "B06": None,
          "B07": None,
          "B8A": None,
          "B11": None,
          "B12": None,
          "SCL": None,
        },
        "60m": {
          "B01": None,
          "B02": None,
          "B03": None,
          "B04": None,
          "B05": None,
          "B06": None,
          "B07": None,
          "B8A": None,
          "B09": None,
          "B11": None,
          "B12": None,
          "SCL": None,        
        },
        "QI": {
            'CLDPRB': None
        }
    }
    
    assert os.path.isdir(safe_folder), f"Could not find folder: {safe_folder}"
    
    bands['QI']['CLDPRB'] = glob(f"{safe_folder}/GRANULE/*/QI_DATA/MSK_CLDPRB_20m.jp2")[0]
    
    bands_10m = glob(f"{safe_folder}/GRANULE/*/IMG_DATA/R10m/*_???_*.jp2")
    for band in bands_10m:
        basename = os.path.basename(band)
        band_name = basename.split('_')[2]
        if band_name == 'B02':
            bands['10m']['B02'] = band
        if band_name == 'B03':
            bands['10m']['B03'] = band
        if band_name == 'B04':
            bands['10m']['B04'] = band
        if band_name == 'B08':
            bands['10m']['B08'] = band

    bands_20m = glob(f"{safe_folder}/GRANULE/*/IMG_DATA/R20m/*.jp2")
    for band in bands_20m:
        basename = os.path.basename(band)
        band_name = basename.split('_')[2]
        if band_name == 'B02':
            bands['20m']['B02'] = band
        if band_name == 'B03':
            bands['20m']['B03'] = band
        if band_name == 'B04':
            bands['20m']['B04'] = band
        if band_name == 'B05':
            bands['20m']['B05'] = band
        if band_name == 'B06':
            bands['20m']['B06'] = band
        if band_name == 'B07':
            bands['20m']['B07'] = band
        if band_name == 'B8A':
            bands['20m']['B8A'] = band
        if band_name == 'B09':
            bands['20m']['B09'] = band
        if band_name == 'B11':
            bands['20m']['B11'] = band
        if band_name == 'B12':
            bands['20m']['B12'] = band
        if band_name == 'SCL':
            bands['20m']['SCL'] = band

    bands_60m = glob(f"{safe_folder}/GRANULE/*/IMG_DATA/R60m/*_???_*.jp2")
    for band in bands_60m:
        basename = os.path.basename(band)
        band_name = basename.split('_')[2]
        if band_name == 'B01':
            bands['60m']['B01'] = band
        if band_name == 'B02':
            bands['60m']['B02'] = band
        if band_name == 'B03':
            bands['60m']['B03'] = band
        if band_name == 'B04':
            bands['60m']['B04'] = band
        if band_name == 'B05':
            bands['60m']['B05'] = band
        if band_name == 'B06':
            bands['60m']['B06'] = band
        if band_name == 'B07':
            bands['60m']['B07'] = band
        if band_name == 'B8A':
            bands['60m']['B8A'] = band
        if band_name == 'B09':
            bands['60m']['B09'] = band
        if band_name == 'B11':
            bands['60m']['B11'] = band
        if band_name == 'B12':
            bands['60m']['B12'] = band
        if band_name == 'SCL':
            bands['60m']['SCL'] = band
    
    for outer_key in bands:
        for inner_key in bands[outer_key]:
            current_band = bands[outer_key][inner_key]
            assert current_band != None, f'{outer_key} - {inner_key} was not found. Verify the folders. Was the decompression interrupted?'

    return bands

def get_metadata(safe_folder):
    metadata = {
        "PRODUCT_START_TIME": None,
        "PRODUCT_STOP_TIME": None,
        "PRODUCT_URI": None,
        "PROCESSING_LEVEL": None,
        "PRODUCT_TYPE": None,
        "PROCESSING_BASELINE": None,
        "GENERATION_TIME": None,
        "SPACECRAFT_NAME": None,
        "DATATAKE_SENSING_START": None,
        "SENSING_ORBIT_NUMBER": None,
        "SENSING_ORBIT_DIRECTION": None,
        "EXT_POS_LIST": None,
        "Cloud_Coverage_Assessment": None,
        "NODATA_PIXEL_PERCENTAGE": None,
        "SATURATED_DEFECTIVE_PIXEL_PERCENTAGE": None,
        "DARK_FEATURES_PERCENTAGE": None,
        "CLOUD_SHADOW_PERCENTAGE": None,
        "VEGETATION_PERCENTAGE": None,
        "NOT_VEGETATED_PERCENTAGE": None,
        "WATER_PERCENTAGE": None,
        "UNCLASSIFIED_PERCENTAGE": None,
        "MEDIUM_PROBA_CLOUDS_PERCENTAGE": None,
        "HIGH_PROBA_CLOUDS_PERCENTAGE": None,
        "THIN_CIRRUS_PERCENTAGE": None,
        "SNOW_ICE_PERCENTAGE": None,
        "folder": safe_folder,
    }

    meta_xml = os.path.join(safe_folder, "MTD_MSIL2A.xml")

    assert os.path.isfile(meta_xml), f"{safe_folder} did not contain a valid metadata file."

    # Parse the xml tree and add metadata
    root = ET.parse(meta_xml).getroot()
    for elem in root.iter():
        if elem.tag in metadata:
            try:
                metadata[elem.tag] = float(elem.text)  # Number?
            except:
                try:
                    metadata[elem.tag] = datetime.datetime.strptime(
                        elem.text, "%Y-%m-%dT%H:%M:%S.%f%z"
                    )  # Date?
                except:
                    metadata[elem.tag] = elem.text

    # Did we get all the metadata?
    for name in metadata:
        assert (
            metadata[name] != None
        ), f"Input metatadata file invalid. {metadata[name]}"

    metadata["INVALID"] = (
        metadata['NODATA_PIXEL_PERCENTAGE']
        + metadata["SATURATED_DEFECTIVE_PIXEL_PERCENTAGE"]
        + metadata["CLOUD_SHADOW_PERCENTAGE"]
        + metadata["MEDIUM_PROBA_CLOUDS_PERCENTAGE"]
        + metadata["HIGH_PROBA_CLOUDS_PERCENTAGE"]
        + metadata["THIN_CIRRUS_PERCENTAGE"]
        + metadata["SNOW_ICE_PERCENTAGE"]
        + metadata["DARK_FEATURES_PERCENTAGE"]
    )
    
    metadata["timestamp"] = float(metadata['DATATAKE_SENSING_START'].timestamp())

    return metadata

def get_time_difference(dict):
    return dict['time_difference']

def assess_radiometric_quality(metadata, calc_quality='high', score=False, previous_b1=None, previous_quality=None):
    if calc_quality == 'high':
        scl = raster_to_array(metadata['path']['20m']['SCL']).astype('intc')
        band_01 = raster_to_array(resample(metadata['path']['60m']['B01'], reference_raster=metadata['path']['20m']['B04'])).astype('intc')
        band_02 = raster_to_array(metadata['path']['20m']['B02']).astype('intc')
        distance = 61
    else:
        scl = raster_to_array(metadata['path']['60m']['SCL']).astype('intc')
        band_01 = raster_to_array(metadata['path']['60m']['B01']).astype('intc')
        band_02 = raster_to_array(metadata['path']['60m']['B02']).astype('intc')
        distance = 21

    kernel = create_kernel(201, weighted_edges=False, weighted_distance=False, normalise=False).astype('uint8')
    kernel_erode = create_kernel(201, weighted_edges=False, weighted_distance=False, normalise=False).astype('uint8')
    
    # Dilate nodata values by 1km each side 
    nodata_dilated = cv2.dilate((scl == 0).astype('uint8'), kernel).astype('intc')
    
    # OBS: the radiometric_quality functions mutates the quality input.
    quality = np.zeros(scl.shape, dtype='intc')
    radiometric_quality(scl, band_01, band_02, nodata_dilated, quality)

    quality_uint8 = quality.astype('uint8')
    quality_eroded = cv2.erode(quality_uint8, kernel_erode).astype('intc')
    quality_mean = cv2.blur(quality_uint8, (distance, distance))
    dist = cv2.distanceTransform((quality_mean > 8).astype('uint8'), cv2.DIST_L2, 5).astype('double')
    
    if calc_quality != 'high':
        dist = np.multiply(dist, 3)

    out_name = metadata['name']

    combined_score = radiometric_quality_spatial(scl, quality, dist, quality_eroded, score)
    
    if score is True:
        return combined_score

    if previous_b1 is not None and previous_quality is not None:
        haze = np.zeros(scl.shape, dtype='intc')
        radiometric_quality_haze(previous_quality, previous_b1, quality, band_01, haze)
    else:
        haze = None

    return quality, scl, band_01, haze

def prepare_metadata(list_of_SAFE_images):

    metadata = []
        # Verify files
    for index, image in enumerate(list_of_SAFE_images):
        image_name = os.path.basename(image)
        assert (len(image_name.split("_")) == 7), f"Input file has invalid pattern: {image_name}"
        assert (image_name.rsplit(".")[1] == "SAFE"), f"Input is not a .SAFE folder: {image_name}"

        # Check if / or // or \\ at end of string, if not attach /
        if image.endswith("//"):
            list_of_SAFE_images[index] = image[:-2]

        if image.endswith("\\"):
            list_of_SAFE_images[index] = image[:-2]

        if image.endswith("/"):
            list_of_SAFE_images[index] = image[:-1]

        # Check if safe folder exists
        assert os.path.isdir(list_of_SAFE_images[index]), f"Could not find input folder: {list_of_SAFE_images[index]}"

        # Check if all images are of the same tile.
        if index == 0:
            tile_name = image_name.split("_")[5]
        else:
            this_tile = image_name.split("_")[5]
            assert (tile_name == this_tile), f"Multiple tiles in inputlist: {tile_name}, {this_tile}"

        image_metadata = get_metadata(list_of_SAFE_images[index])
        image_metadata['path'] = get_band_paths(list_of_SAFE_images[index])
        image_metadata['name'] = os.path.basename(os.path.normpath(image_metadata['folder'])).split('_')[-1].split('.')[0]
        metadata.append(image_metadata)

    lowest_invalid_percentage = 100
    best_image = None
    
    best_images_names = []
    best_images = []
    
    # Find the image with the lowest invalid percentage
    for meta in metadata:
        if meta['INVALID'] < lowest_invalid_percentage:
            lowest_invalid_percentage = meta['INVALID']
            best_image = meta

    for meta in metadata:
        if (meta['INVALID'] - lowest_invalid_percentage) <= 10:
            if meta['name'] not in best_images_names:
                best_images.append(meta)
                best_images_names.append(meta['name'])

    if len(best_images) != 1:
        # Search the top 10% images for the best image
        max_quality_score = 0
        for image in best_images:
            quality_score = assess_radiometric_quality(image, calc_quality='low', score=True)

            if quality_score > max_quality_score:
                max_quality_score = quality_score
                best_image = image

    # Calculate the time difference from each image to the best image
    for meta in metadata:
        meta['time_difference'] = abs(meta['timestamp'] - best_image['timestamp'])

    # Sort by distance to best_image
    metadata = sorted(metadata, key=lambda k: k['time_difference']) 
    
    return metadata

# TODO: For the simple harmonisation method: exclude quality < 8, decreasing until critical mass (~1% cover) 
# TODO: Work on double for quality testing. Do linear functions instead of thresholding..

# TODO: Find out what is wrong with: ['30NYL', '30PWR', '30PXR', '30PXS', '30PYQ', '30NWN', '30NZM', '30NZP']
# TODO: Add multiprocessing
# TODO: Add overlap harmonisation
# TODO: handle all bands
# TODO: add pansharpen
# TODO: ai resample of SWIR

def mosaic_tile(
    list_of_SAFE_images,
    out_dir,
    out_name='mosaic',
    dst_projection=None,
    feather=True,
    ideal_percent=99,
    feather_dist=31,
    filter_tracking=True,
    filter_tracking_dist=7,
    filter_tracking_iterations=1,
    match_mean=True,
    match_simple=True,
    noise_reduction=True,
    max_days=30,
    max_images_include=15,
    max_search_images=35,
):
    start_time = time()

    # Verify input
    assert isinstance(list_of_SAFE_images, list), "list_of_SAFE_images is not a list. [path_to_safe_file1, path_to_safe_file2, ...]"
    assert isinstance(out_dir, str), f"out_dir is not a string: {out_dir}"
    assert isinstance(out_name, str), f"out_name is not a string: {out_name}"
    assert len(list_of_SAFE_images) > 1, "list_of_SAFE_images is empty or only a single image."

    print('Selecting best image..')
    metadata = prepare_metadata(list_of_SAFE_images)
    
    # Sorted by best, so 0 is the best one.
    best_image = metadata[0]
    best_image_name = best_image['name']

    print(f'Selected: {best_image_name}')

    print('Resampling and reading base image..')
    quality, scl, b1, haze = assess_radiometric_quality(best_image)
    tracking_array = np.zeros(quality.shape, dtype='uint8')
    
    if match_mean is True:
        metadata[0]['scl'] = np.copy(scl)
        metadata[0]['quality'] = quality.astype('uint8')
  
    time_limit = (max_days * 86400)
    avg_quality = (quality.sum() / quality.size) * 10
    i = 1  # The 0 index is for the best image
    processed_images_indices = [0]

    print(f'Initial. tracking array: (quality {round(avg_quality, 2)}%) (0/{max_days} days) (goal {ideal_percent}%)')
    # Loop the images and update the tracking array
    while (
        (avg_quality < ideal_percent)
        and i < len(metadata) - 1
        and i <= max_search_images
        and len(processed_images_indices) <= max_images_include
        and (metadata[i]['time_difference'] < time_limit)
    ):
        ex_quality, ex_scl, ex_b1, ex_haze = assess_radiometric_quality(metadata[i], previous_b1=b1, previous_quality=quality)
        
        # Time difference
        td = int(round(metadata[i]['time_difference'] / 86400, 0))  

        change_mask = np.zeros(ex_scl.shape, dtype='intc')
        radiometric_change_mask(quality, ex_quality, scl, ex_scl, ex_haze, change_mask)
        change_mask = change_mask.astype('bool')

        ex_quality_test = np.where(change_mask, ex_quality, quality).astype('uint8')
        ex_quality_avg = (ex_quality_test.sum() / ex_quality_test.size) * 10

        # exponential decrease of threshold
        threshold = 2.0012 * math.exp(-0.028135 * avg_quality)

        if (ex_quality_avg - avg_quality) > threshold:
            
            # Udpdate the trackers
            tracking_array = np.where(change_mask, i, tracking_array).astype('uint8')
            scl = np.where(change_mask, ex_scl, scl).astype('intc')
            b1 = np.where(change_mask, ex_b1, b1).astype('intc')

            if match_mean is True:
                metadata[i]['scl'] = ex_scl
                metadata[i]['quality'] = ex_quality_test

            quality = ex_quality_test.astype('intc')

            avg_quality = (quality.sum() / quality.size) * 10

            processed_images_indices.append(i)

            img_name = os.path.basename(os.path.normpath(metadata[i]['folder'])).split('_')[-1].split('.')[0]

            print(f'Updating tracking array: (quality {round(avg_quality, 2)}%) ({td}/{max_days} days) (goal {ideal_percent}%) (name {img_name})')
        else:
            print(f'Skipping image due to low change.. ({round(threshold, 3)}% threshold) ({td}/{max_days} days)')

        i += 1


    multiple_images = len(processed_images_indices) > 1

    # Only merge images if there are more than one.
    if match_mean is True and multiple_images is True:

        print('Harmonising layers..')
        
        if match_simple is True:
            total_counts = 0
            counts = []
            weights = []
            
            for i in processed_images_indices:
                metadata[i]['stats'] = { 'B02': {}, 'B03': {}, 'B04': {}, 'B08': {} }
                pixel_count = (tracking_array == i).sum()
                total_counts += pixel_count
                counts.append(pixel_count)
                metadata[i]['pixel_count'] = pixel_count
            
            for i in range(len(processed_images_indices)):
                weights.append(counts[i] / total_counts)

            medians = { 'B02': [], 'B03': [], 'B04': [], 'B08': [] }
            madstds = { 'B02': [], 'B03': [], 'B04': [], 'B08': [] }

            for v, i in enumerate(processed_images_indices):
                pixel_cutoff = 1 / quality.size
                
                if metadata[i]['pixel_count'] < pixel_cutoff:
                    layer_mask = np.full(quality.shape, False)
                else:
                    quality_cutoff = 10
                    land_mask = (metadata[i]['scl'] == 4) | (metadata[i]['scl'] == 5) | (metadata[i]['scl'] == 7)
                    quality_mask = metadata[i]['quality'] < quality_cutoff
                    
                    layer_mask = quality_mask & land_mask
                    
                    add_water = False
                    while layer_mask.sum() < pixel_cutoff:
                        quality_cutoff -= 1
                        if quality_cutoff < 7:
                            add_water = True
                            break
                        quality_mask = metadata[i]['quality'] < quality_cutoff
                        layer_mask = quality_mask & land_mask
                    
                    if add_water is True:
                        quality_cutoff = 10
                        land_mask = (metadata[i]['scl'] == 4) | (metadata[i]['scl'] == 5) | (metadata[i]['scl'] == 6) | (metadata[i]['scl'] == 7)
                        quality_mask = metadata[i]['quality'] < quality_cutoff
                        layer_mask = quality_mask & land_mask
                        
                        add_all = False
                        while layer_mask.sum() < pixel_cutoff:
                            quality_cutoff -= 1
                            if quality_cutoff < 5:
                                add_all = True
                                break
                            quality_mask = metadata[i]['quality'] < quality_cutoff
                            layer_mask = quality_mask & land_mask
                        
                        if add_all == True:
                            quality_cutoff = 10
                            quality_mask = metadata[i]['quality'] < quality_cutoff
                            layer_mask = quality_mask
                            
                            while layer_mask.sum() < pixel_cutoff:
                                quality_cutoff -= 1
                                quality_mask = metadata[i]['quality'] < quality_cutoff
                                layer_mask = quality_mask
                

                for band in ['B02', 'B03', 'B04', 'B08']:
                    if band == 'B08':
                        array = raster_to_array(resample(metadata[i]['path']['10m'][band], reference_raster=metadata[i]['path']['20m']['B02']))
                    else:
                        array = raster_to_array(metadata[i]['path']['20m'][band])

                    calc_array = np.ma.array(array, mask=layer_mask)
                    med, mad = madstd(calc_array)

                    if med == 0 or mad == 0:
                        med, mad = madstd(array)
                        
                    medians[band].append(med)
                    madstds[band].append(mad)
            
            targets_median = { 'B02': None, 'B03': None, 'B04': None, 'B08': None }
            targets_madstd = { 'B02': None, 'B03': None, 'B04': None, 'B08': None }
            
            for band in ['B02', 'B03', 'B04', 'B08']:
                targets_median[band] = np.average(medians[band], weights=weights)
                targets_madstd[band] = np.average(madstds[band], weights=weights)
        
            for v, i in enumerate(processed_images_indices):
                for band in ['B02', 'B03', 'B04', 'B08']:
                    metadata[i]['stats'][band]['src_median'] = medians[band][v] if medians[band][v] > 0 else targets_median[band]
                    metadata[i]['stats'][band]['src_madstd'] = madstds[band][v] if madstds[band][v] > 0 else targets_madstd[band]
                    metadata[i]['stats'][band]['target_median'] = targets_median[band]
                    metadata[i]['stats'][band]['target_madstd'] = targets_madstd[band]
        
        else:
            veg_mask = scl == 4
            non_veg_mask = scl == 5
            unclassified_mask = scl == 7
            water_mask = scl == 6
        
            for i in processed_images_indices:                
                metadata[i]['stats'] = {
                    'B02': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0, 'scale': 1 },
                    'B03': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0, 'scale': 1 },
                    'B04': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0, 'scale': 1 },
                    'B08': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0, 'scale': 1 },
                    'counts': {
                        'vegetation': 0,
                        'not_vegetation': 0,
                        'unclassified': 0,
                        'water': 0,
                    },
                }
                
                # Prepare masks
                layer_mask = tracking_array == i
                
                # If not atleast 0.5% of pixels are included - exclude the image.
                if (layer_mask.sum() / layer_mask.size) * 100 < 0.5:
                    metadata[i]['stats']['counts']['vegetation'] = 0
                    metadata[i]['stats']['counts']['not_vegetation'] = 0
                    metadata[i]['stats']['counts']['unclassified'] = 0
                    metadata[i]['stats']['counts']['water'] = 0
                else:
                    layer_veg = layer_mask & veg_mask
                    layer_non_veg = layer_mask & non_veg_mask
                    layer_unclassified = layer_mask & unclassified_mask
                    layer_water = layer_mask & water_mask
                        
                    # Calculate count of pixels
                    metadata[i]['stats']['counts']['vegetation'] = layer_veg.sum()
                    metadata[i]['stats']['counts']['not_vegetation'] = layer_non_veg.sum()
                    metadata[i]['stats']['counts']['unclassified'] = layer_unclassified.sum()
                    metadata[i]['stats']['counts']['water'] = layer_water.sum()
                
                # Free memory again
                layer_mask = None
                layer_veg = None
                layer_non_veg = None
                layer_unclassified = None
                layer_water = None
                
                # Calculate the mean values for each band
                for band in ['B02', 'B03', 'B04', 'B08']:
                    if band == 'B08': # No 20m B08 from ESA
                        array = raster_to_array(resample(metadata[i]['path']['10m'][band], reference_raster=metadata[i]['path']['20m']['B02']))
                    else:
                        array = raster_to_array(metadata[i]['path']['20m'][band])

                    zero_mask = array == 0

                    med, mad = madstd(np.ma.array(array, mask=metadata[i]['scl'] != 4 | zero_mask))
                    metadata[i]['stats'][band]['vegetation'] = med
                    metadata[i]['stats'][band]['vegetation_mad'] = mad

                    med, mad = madstd(np.ma.array(array, mask=metadata[i]['scl'] != 5 | zero_mask))
                    metadata[i]['stats'][band]['not_vegetation'] = med
                    metadata[i]['stats'][band]['not_vegetation_mad'] = mad
                
                    med, mad = madstd(np.ma.array(array, mask=metadata[i]['scl'] != 7 | zero_mask))
                    metadata[i]['stats'][band]['unclassified'] = med
                    metadata[i]['stats'][band]['unclassified_mad'] = mad
                    
                    med, mad = madstd(np.ma.array(array, mask=metadata[i]['scl'] != 6 | zero_mask))
                    metadata[i]['stats'][band]['water'] = med
                    metadata[i]['stats'][band]['water_mad'] = mad

            pixel_sums = {
                'vegetation': 0,
                'not_vegetation': 0,
                'unclassified': 0,
                'water': 0,
                'valid_ground_pixels': 0,             
            }
            
            medians = {
                'B02': { 'vegetation': [], 'not_vegetation': [], 'unclassified': [], 'water': [] },
                'B03': { 'vegetation': [], 'not_vegetation': [], 'unclassified': [], 'water': [] },
                'B04': { 'vegetation': [], 'not_vegetation': [], 'unclassified': [], 'water': [] },
                'B08': { 'vegetation': [], 'not_vegetation': [], 'unclassified': [], 'water': [] },
            }
            
            madstds = {
                'B02': { 'vegetation': [], 'not_vegetation': [], 'unclassified': [], 'water': [] },
                'B03': { 'vegetation': [], 'not_vegetation': [], 'unclassified': [], 'water': [] },
                'B04': { 'vegetation': [], 'not_vegetation': [], 'unclassified': [], 'water': [] },
                'B08': { 'vegetation': [], 'not_vegetation': [], 'unclassified': [], 'water': [] },
            }
            
            for i in processed_images_indices:
                image = metadata[i]
                counts = [
                    image['stats']['counts']['vegetation'],
                    image['stats']['counts']['not_vegetation'],
                    image['stats']['counts']['unclassified'],
                    image['stats']['counts']['water'],
                ]
                pixel_sums['vegetation'] += counts[0]
                pixel_sums['not_vegetation'] += counts[1]
                pixel_sums['unclassified'] += counts[2]
                pixel_sums['water'] += counts[3]
                pixel_sums['valid_ground_pixels'] += sum(counts)
                
                for band in ['B02', 'B03', 'B04', 'B08']:
                    medians[band]['vegetation'].append(image['stats'][band]['vegetation'])
                    madstds[band]['vegetation'].append(image['stats'][band]['vegetation_mad'])
                    
                    medians[band]['not_vegetation'].append(image['stats'][band]['not_vegetation'])
                    madstds[band]['not_vegetation'].append(image['stats'][band]['not_vegetation_mad'])
                    
                    medians[band]['unclassified'].append(image['stats'][band]['unclassified'])
                    madstds[band]['unclassified'].append(image['stats'][band]['unclassified_mad'])
                    
                    medians[band]['water'].append(image['stats'][band]['water'])
                    madstds[band]['water'].append(image['stats'][band]['water_mad'])

            ratios = {
                'vegetation': pixel_sums['vegetation'] / pixel_sums['valid_ground_pixels'],
                'not_vegetation': pixel_sums['not_vegetation'] / pixel_sums['valid_ground_pixels'],
                'unclassified': pixel_sums['unclassified'] / pixel_sums['valid_ground_pixels'],
                'water': pixel_sums['water'] / pixel_sums['valid_ground_pixels'],
            }

            weights = { 'vegetation': [], 'not_vegetation': [], 'unclassified': [], 'water': [] }
            
            for i in processed_images_indices:
                image = metadata[i]

                if pixel_sums['vegetation'] == 0:
                    weights['vegetation'].append(0)
                else:
                    weights['vegetation'].append(image['stats']['counts']['vegetation'] / pixel_sums['vegetation'])

                if pixel_sums['not_vegetation'] == 0:
                    weights['not_vegetation'].append(0)
                else:
                    weights['not_vegetation'].append(image['stats']['counts']['not_vegetation'] / pixel_sums['not_vegetation'])

                if pixel_sums['unclassified'] == 0:
                    weights['unclassified'].append(0)
                else:
                    weights['unclassified'].append(image['stats']['counts']['unclassified'] / pixel_sums['unclassified'])
                    
                if pixel_sums['unclassified'] == 0:
                    weights['water'].append(0)
                else:
                    weights['water'].append(image['stats']['counts']['water'] / pixel_sums['water'])
        
            weighted_medians = {
                'B02': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0 },
                'B03': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0 },
                'B04': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0 },
                'B08': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0 },
            }
            
            weighted_madstds = {
                'B02': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0 },
                'B03': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0 },
                'B04': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0 },
                'B08': { 'vegetation': 0, 'not_vegetation': 0, 'unclassified': 0, 'water': 0 },
            }
            
            targets_median = { 'B02': None, 'B03': None, 'B04': None, 'B08': None }
            targets_madstd = { 'B02': None, 'B03': None, 'B04': None, 'B08': None }
            
            for band in ['B02', 'B03', 'B04', 'B08']:
                weighted_medians[band]['vegetation'] = np.average(medians[band]['vegetation'], weights=weights['vegetation'])
                weighted_medians[band]['unclassified'] = np.average(medians[band]['unclassified'], weights=weights['unclassified'])
                weighted_medians[band]['not_vegetation'] = np.average(medians[band]['not_vegetation'], weights=weights['not_vegetation'])
                weighted_medians[band]['water'] = np.average(medians[band]['water'], weights=weights['water'])
                
                weighted_madstds[band]['vegetation'] = np.average(madstds[band]['vegetation'], weights=weights['vegetation'])
                weighted_madstds[band]['not_vegetation'] = np.average(madstds[band]['not_vegetation'], weights=weights['not_vegetation'])
                weighted_madstds[band]['unclassified'] = np.average(madstds[band]['unclassified'], weights=weights['unclassified'])
                weighted_madstds[band]['water'] = np.average(madstds[band]['water'], weights=weights['water'])
                
                targets_median[band] = sum([
                    ratios['vegetation'] * weighted_medians[band]['vegetation'],
                    ratios['not_vegetation'] * weighted_medians[band]['not_vegetation'],
                    ratios['unclassified'] * weighted_medians[band]['unclassified'],
                    ratios['water'] * weighted_medians[band]['water'],
                ])
                
                targets_madstd[band] = sum([
                    ratios['vegetation'] * weighted_madstds[band]['vegetation'],
                    ratios['not_vegetation'] * weighted_madstds[band]['not_vegetation'],
                    ratios['unclassified'] * weighted_madstds[band]['unclassified'],
                    ratios['water'] * weighted_madstds[band]['water'],
                ])
                
                import pdb; pdb.set_trace()
            
            for i in processed_images_indices:
                for band in ['B02', 'B03', 'B04', 'B08']:

                    if pixel_sums['valid_ground_pixels'] == 0:
                        raise Exception('No valid pixels in selected image band.')
                    else:
                        src_median = sum([
                            ratios['vegetation'] * metadata[i]['stats'][band]['vegetation'],
                            ratios['not_vegetation'] * metadata[i]['stats'][band]['not_vegetation'],
                            ratios['unclassified'] * metadata[i]['stats'][band]['unclassified'],
                            ratios['water'] * metadata[i]['stats'][band]['water'],
                        ])
                        
                        src_madstd = sum([
                            ratios['vegetation'] * metadata[i]['stats'][band]['vegetation_mad'],
                            ratios['not_vegetation'] * metadata[i]['stats'][band]['not_vegetation_mad'],
                            ratios['unclassified'] * metadata[i]['stats'][band]['unclassified_mad'],
                            ratios['water'] * metadata[i]['stats'][band]['water_mad'],
                        ])
                        
                        metadata[i]['stats'][band]['src_median'] = src_median if src_median > 0 else targets_median[band]
                        metadata[i]['stats'][band]['src_madstd'] = src_madstd if src_madstd > 0 else targets_madstd[band]
                        metadata[i]['stats'][band]['target_median'] = targets_median[band]
                        metadata[i]['stats'][band]['target_madstd'] = targets_madstd[band]
                    

    # Resample scl and tracking array
    tracking_array = raster_to_array(resample(array_to_raster(tracking_array, reference_raster=best_image['path']['20m']['B04']), reference_raster=best_image['path']['10m']['B04']))
    scl = raster_to_array(resample(array_to_raster(scl, reference_raster=best_image['path']['20m']['B04']), reference_raster=best_image['path']['10m']['B04']))

    if filter_tracking is True and multiple_images is True:
        print('Filtering tracking array..')
        # Run a mode filter on the tracking arrayclear
        tracking_array = mode_filter(tracking_array, filter_tracking_dist, filter_tracking_iterations).astype('uint8')
    
    array_to_raster(tracking_array.astype('uint8'), reference_raster=best_image['path']['10m']['B08'], out_raster=os.path.join(out_dir, f"tracking_{out_name}.tif"), dst_projection=dst_projection)

    if feather and multiple_images is True:
        print('Precalculating feathers..')
        feathers = {}
        for i in processed_images_indices:
            feathers[str(i)] = feather_s2_filter(tracking_array, i, feather_dist).astype('float32')

    array_to_raster(scl.astype('uint8'), reference_raster=best_image['path']['10m']['B08'], out_raster=os.path.join(out_dir, f"slc_{out_name}.tif"), dst_projection=dst_projection)

    bands_to_output = ['B02', 'B03', 'B04', 'B08']
    print('Merging band data..')
    for band in bands_to_output:
        print(f'Writing: {band}..')
        base_image = raster_to_array(metadata[0]['path']['10m'][band]).astype('float32')

        for i in processed_images_indices:

            if match_mean and len(processed_images_indices) > 1:
                src_med = metadata[i]['stats'][band]['src_median']
                src_mad = metadata[i]['stats'][band]['src_madstd']
                target_med = metadata[i]['stats'][band]['target_median']
                target_mad = metadata[i]['stats'][band]['target_madstd']

            if i == 0:
                if match_mean and len(processed_images_indices) > 1:
                    dif = (base_image - src_med)
                    base_image = ((dif * target_mad) / src_mad) + target_med
                    base_image = np.where(base_image >= 0, base_image, 0)
                    
                if feather is True and len(processed_images_indices) > 1:
                    base_image = base_image * feathers[str(i)]

            else:
                add_band = raster_to_array(metadata[i]['path']['10m'][band]).astype('float32')
                
                if match_mean:                    
                    dif = (add_band - src_med)
                    add_band = ((dif * target_mad) / src_mad) + target_med
                    add_band = np.where(add_band >= 0, add_band, 0)
            
                if feather is True:
                    base_image = np.add(base_image, (add_band * feathers[str(i)]))
                else:
                    base_image = np.where(tracking_array == i, add_band, base_image).astype('float32')

        if noise_reduction is True:
            export_layer = median_filter(base_image)
        else:
            export_layer = base_image

        array_to_raster(np.rint(base_image).astype('uint16'), reference_raster=best_image['path']['10m'][band], out_raster=os.path.join(out_dir, f"{band}_{out_name}.tif"), dst_projection=dst_projection)

    print(f'Completed mosaic in: {round((time() - start_time) / 60, 1)}m')
