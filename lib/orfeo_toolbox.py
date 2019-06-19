import subprocess
import psutil
import os
import sys
import time
import json
from utils import progress
from raster_to_array import raster_to_array


config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.json')
if os.path.exists(config_path) is True:
    config = json.load(open(config_path))
    otb_folder = os.path.abspath(config['Orfeo-Toolbox']['path'])
else:
    otb_folder = os.path.abspath('../OTB/bin/')


def execute_cli_function(command, name, quiet=False):
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    try:
        before = time.time()
        for line in iter(process.stdout.readline, ''):
            if 'FATAL' in line:
                raise RuntimeError(line)
            elif 'CRITICAL' in line:
                raise RuntimeError(line)
            elif 'WARNING' in line:
                continue
            elif quiet is False:
                if 'INFO' in line:
                    continue
            try:
                strip = line.strip()
                if len(strip) != 0:
                    part = strip.rsplit(':', 1)[1]
                    percent = int(part.split('%')[0])
                    progress(percent, 100, name)
            except:
                if len(line.strip()) != 0:
                    raise RuntimeError(line) from None
    except:
        raise RuntimeError('Critical failure while performing Orfeo-Toolbox action.')

    print(f'{name} completed in {round(time.time() - before, 2)}s.')


def pansharpen(in_pan, in_xs, out_raster, options=None, out_datatype=None):
    ''' Pansharpen an image using the attributes
        of another image. Beware that the two images
        should be of the same size and position. '''

    cli = os.path.join(otb_folder, 'otbcli_Pansharpening.bat')

    ''' *******************************************************
        Parse the input and create CLI string
    ******************************************************* '''
    methods = ['rcs', 'lmvm', 'bayes']

    if options is None:
        options = {
            'method': 'lmvm',
            'method.lmvm.radiusx': 3,
            'method.lmvm.radiusy': 3,
        }

    if options['method'] not in methods:
        raise AttributeError('Selected method is not available.')

    if options['method'] == 'lmvm':
        if 'method.lmvm.radiusx' not in options:
            options['method.lmvm.radiusx'] = 3
        if 'method.lmvm.radiusx' not in options:
            options['method.lmvm.radiusx'] = 3
    if options['method'] == 'bayes':
        if 'method.bayes.lamda' not in options:
            options['method.bayes.lamda'] = 0.9999
        if 'method.bayes.s' not in options:
            options['method.bayes.s'] = 1

    if out_datatype is None:
        out_datatype = ''

    cli_args = [cli, '-inp', os.path.abspath(in_pan), '-inxs', os.path.abspath(in_xs), '-out', f'"{os.path.abspath(out_raster)}?&gdal:co:COMPRESS=DEFLATE&gdal:co:NUM_THREADS=ALL_CPUS&gdal:co:BIGTIFF=YES"', out_datatype]

    for key, value in options.items():
        cli_args.append('-' + str(key))
        cli_args.append(str(value))

    cli_string = ' '.join(cli_args)

    ''' *******************************************************
        Make CLI request and handle responses
    ******************************************************* '''

    execute_cli_function(cli_string, name='Pansharpening')

    return os.path.abspath(out_raster)


def local_stats(in_raster, out_raster, options=None, band=None):
    ''' Computes local statistical moments on every pixel
        in the selected channel of the input image '''

    cli = os.path.join(otb_folder, 'otbcli_LocalStatisticExtraction.bat')

    if options is None:
        options = {
            'channel': 1,
            'radius': 2,
        }

    if band is not None:
        band = f'&bands={band}'
    else:
        band = ''

    # Set RAM to 90% of available ram.
    if 'ram' not in options:
        options['ram'] = int((psutil.virtual_memory().available / (1024.0 * 1024.0)) * 0.9)

    cli_args = [cli, '-in', os.path.abspath(in_raster), '-out', f'"{os.path.abspath(out_raster)}?{band}&gdal:co:COMPRESS=DEFLATE&gdal:co:PREDICTOR=3&gdal:co:NUM_THREADS=ALL_CPUS&gdal:co:BIGTIFF=YES" float']

    for key, value in options.items():
        cli_args.append('-' + str(key))
        cli_args.append(str(value))

    cli_string = ' '.join(cli_args)

    ''' *******************************************************
        Make CLI request and handle responses
    ******************************************************* '''

    execute_cli_function(cli_string, name='Local statistics')

    return os.path.abspath(out_raster)


def haralick(in_raster, out_raster, options=None, out_datatype='float', band=None):
    ''' Performs haralick texture extraction '''

    cli = os.path.join(otb_folder, 'otbcli_HaralickTextureExtraction.bat')

    stats_raster = raster_to_array(in_raster)
    stats = {'min': stats_raster.min(), 'max': stats_raster.max()}
    stats_raster = None

    if options is None:
        options = {
            'texture': 'simple',
            'channel': 1,
            'parameters.nbbin': 32,
            'parameters.xrad': 2,
            'parameters.yrad': 2,
            'parameters.min': stats['min'],
            'parameters.max': stats['max'],
        }

    if out_datatype is None:
        out_datatype = 'float'

    if band is not None:
        band = f'&bands={band}'
    else:
        band = ''

    # Set RAM to 90% of available ram.
    if 'ram' not in options:
        options['ram'] = int((psutil.virtual_memory().available / (1024.0 * 1024.0)) * 0.9)

    cli_args = [cli, '-in', os.path.abspath(in_raster), '-out', f'"{os.path.abspath(out_raster)}?{band}&gdal:co:COMPRESS=DEFLATE&gdal:co:NUM_THREADS=ALL_CPUS&gdal:co:BIGTIFF=YES"', out_datatype]

    for key, value in options.items():
        cli_args.append('-' + str(key))
        cli_args.append(str(value))

    cli_string = ' '.join(cli_args)

    ''' *******************************************************
        Make CLI request and handle responses
    ******************************************************* '''

    execute_cli_function(cli_string, name='Texture extraction')

    return os.path.abspath(out_raster)


def dimension_reduction(in_raster, out_raster, options=None, out_datatype=None):
    ''' Performs dimensionality reduction on input image.
        PCA,NA-PCA,MAF,ICA methods are available.
        It is also possible to compute the inverse transform
        to reconstruct the image. It is also possible to
        optionally export the transformation matrix
        to a text file. '''

    cli = os.path.join(otb_folder, 'otbcli_DimensionalityReduction.bat')

    if options is None:
        options = {
            'method': 'pca',
            'rescale.outmin': 0,
            'rescale.outmax': 1,
            'nbcomp': 1,
            'normalize': 'YES',
        }

    if out_datatype is None:
        out_datatype = ''

    # Set RAM to 90% of available ram.
    if 'ram' not in options:
        options['ram'] = int((psutil.virtual_memory().available / (1024.0 * 1024.0)) * 0.9)

    cli_args = [cli, '-in', os.path.abspath(in_raster), '-out', f'"{os.path.abspath(out_raster)}?&gdal:co:COMPRESS=DEFLATE&gdal:co:NUM_THREADS=ALL_CPUS&gdal:co:BIGTIFF=YES"', out_datatype]

    for key, value in options.items():
        cli_args.append('-' + str(key))
        cli_args.append(str(value))

    cli_string = ' '.join(cli_args)

    ''' *******************************************************
        Make CLI request and handle responses
    ******************************************************* '''

    execute_cli_function(cli_string, name='Dimension reduction')

    return os.path.abspath(out_raster)


def concatenate_images(in_rasters, out_raster, ram=None, out_datatype=None):
    ''' This application performs images channels concatenation.
    It reads the input image list (single or multi-channel) and
    generates a single multi-channel image. The channel order
    is the same as the list. '''

    cli = os.path.join(otb_folder, 'otbcli_ConcatenateImages.bat')

    paths = []
    for raster in in_rasters:
        paths.append(os.path.abspath(raster))
    paths = ' '.join(paths)

    if out_datatype is None:
        out_datatype = ''

    # Set RAM to 90% of available ram.
    if ram is None:
        ram = int((psutil.virtual_memory().available / (1024.0 * 1024.0)) * 0.9)

    cli_string = ' '.join([cli, '-il', os.path.abspath(paths), '-out', f'"{os.path.abspath(out_raster)}?&gdal:co:COMPRESS=DEFLATE&gdal:co:NUM_THREADS=ALL_CPUS&gdal:co:BIGTIFF=YES"', out_datatype, '-ram', str(ram)])

    ''' *******************************************************
        Make CLI request and handle responses
    ******************************************************* '''

    execute_cli_function(cli_string, name='concatenate images')

    return os.path.abspath(out_raster)


def split_images(in_raster, out_rasters, ram=None, out_datatype=None):
    ''' This application splits a N-bands image into N mono-band images.
        The output images filename will be generated from the output parameter.
        Thus, if the input image has 2 channels, and the user has set as
        output parameter, outimage.tif, the generated images will be
        outimage_0.tif and outimage_1.tif. '''

    cli = os.path.join(otb_folder, 'otbcli_SplitImage.bat')

    # Set RAM to 90% of available ram.
    if ram is None:
        ram = int((psutil.virtual_memory().available / (1024.0 * 1024.0)) * 0.9)

    if out_datatype is None:
        out_datatype = ''

    cli_string = ' '.join([cli, '-in', os.path.abspath(in_raster), '-out', f'"{os.path.abspath(out_rasters)}?&gdal:co:COMPRESS=DEFLATE&gdal:co:NUM_THREADS=ALL_CPUS&gdal:co:BIGTIFF=YES"', out_datatype, '-ram', str(ram)])

    ''' *******************************************************
        Make CLI request and handle responses
    ******************************************************* '''

    execute_cli_function(cli_string, name='splitting images')

    return out_rasters


def rescale(in_raster, out_raster, options=None, out_datatype='float'):
    ''' This application scales the given image pixel intensity between two given values.
        By default min (resp. max) value is set to 0 (resp. 1).
        Input minimum and maximum values is automatically computed for all image bands. '''

    cli = os.path.join(otb_folder, 'otbcli_Rescale.bat')

    if options is None:
        options = {
            'outmin': 0,
            'outmax': 1,
        }

    if out_datatype == 'float':
        predictor = 'gdal:co:PREDICTOR=3&'
    elif out_datatype == 'uint16':
        predictor = 'gdal:co:PREDICTOR=2&'
    else:
        predictor = ''

    # Set RAM to 90% of available ram.
    if 'ram' not in options:
        options['ram'] = int((psutil.virtual_memory().available / (1024.0 * 1024.0)) * 0.9)

    cli_args = [cli, '-in', os.path.abspath(in_raster), '-out', f'"{os.path.abspath(out_raster)}?&gdal:co:COMPRESS=DEFLATE&{predictor}gdal:co:NUM_THREADS=ALL_CPUS&gdal:co:BIGTIFF=YES"', out_datatype]

    for key, value in options.items():
        cli_args.append('-' + str(key))
        cli_args.append(str(value))

    cli_string = ' '.join(cli_args)

    ''' *******************************************************
        Make CLI request and handle responses
    ******************************************************* '''

    execute_cli_function(cli_string, name='rescale image')

    return os.path.abspath(out_raster)


def merge_rasters(in_rasters, out_raster, options=None, band=None, out_datatype='uint16'):
    ''' Creates a mosaic out of a series of images. Must be of the same projection '''

    cli = os.path.join(otb_folder, 'otbcli_Mosaic.bat')

    if options is None:
        options = {
            'comp.feather': 'large',
            'harmo.method': 'band',
        }

    if band is not None:
        band = f'&bands={band}'
    else:
        band = ''

    cli_args = [cli, '-il', ' '.join(in_rasters), '-out', f'"{os.path.abspath(out_raster)}?{band}&gdal:co:COMPRESS=DEFLATE&gdal:co:NUM_THREADS=ALL_CPUS&gdal:co:BIGTIFF=YES"', out_datatype]

    for key, value in options.items():
        cli_args.append('-' + str(key))
        cli_args.append(str(value))

    cli_string = ' '.join(cli_args)

    ''' *******************************************************
        Make CLI request and handle responses
    ******************************************************* '''

    execute_cli_function(cli_string, name='merge rasters')

    return os.path.abspath(out_raster)