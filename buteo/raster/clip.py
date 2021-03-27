import sys; sys.path.append('../../')
from osgeo import gdal, ogr, osr
from typing import Union
from buteo.raster.io import raster_to_metadata
from buteo.vector.io import vector_to_metadata, vector_to_memory, reproject_vector
from buteo.utils import remove_if_overwrite
from buteo.gdal_utils import (
    raster_to_reference,
    vector_to_reference,
    is_raster,
    is_vector,
    path_to_driver,
    default_options,
    translate_resample_method,
    gdal_nodata_value_from_type,
    align_bbox,
)


# TODO: Test this for robustness, other projections and speed.
# TODO: enable layer selection or always use all.
def clip_raster(
    raster: Union[str, gdal.Dataset],
    clip_geom: Union[str, ogr.DataSource],
    out_path: Union[str, None]=None,
    resample_alg: str="nearest",
    crop_to_geom: bool=True,
    all_touch: bool=False,
    overwrite: bool=True,
    adjust_bbox: bool=True,
    creation_options: list=[],
    dst_nodata: Union[str, int, float]="infer",
    layer_to_clip: Union[str, int]="first",
) -> Union[gdal.Dataset, str]:
    """ Clips a raster using a vector geometry or the extents of
        a raster.

    Args:
        raster (path | raster): The raster to clip.
        
        clip_geom (path | vector | raster): The geometry to use to clip
        the raster

    **kwargs:
        out_path (path | None): The destination to save to. If None then
        the output is an in-memory raster.

        resample_alg (str): The algorithm to resample the raster. The following
        are available:
            'nearest', 'bilinear', 'cubic', 'cubicSpline', 'lanczos', 'average',
            'mode', 'max', 'min', 'median', 'q1', 'q3', 'sum', 'rms'.
        
        crop_to_geom (bool): Should the extent of the raster be clipped
        to the extent of the clipping geometry.

        all_touch (bool): Should all the pixels touched by the clipped 
        geometry be included or only those which centre lie within the
        geometry.

        overwite (bool): Is it possible to overwrite the out_path if it exists.

        creation_options (list): A list of options for the GDAL creation. Only
        used if an outpath is specified. Defaults are:
            "TILED=YES"
            "NUM_THREADS=ALL_CPUS"
            "BIGG_TIF=YES"
            "COMPRESS=LZW"

        dst_nodata (str | int | float): If dst_nodata is 'infer' the destination nodata
        is the src_nodata if one exists, otherwise it's automatically chosen based
        on the datatype. If an int or a float is given, it is used as the output nodata.

        layer_to_clip (str, int): The layer in the input vector to use for clipping.
        If  layer_to_clip is "first" the first layer in the vector is used. If "all",
        all layers a used to process. An INT can be passed to use a specific layer.


    Returns:
        An in-memory raster. If an out_path is given the output is a string containing
        the path to the newly created raster.
    """

    # Verify inputs
    ref = raster_to_reference(raster)
    metadata = raster_to_metadata(ref)
    
    # Verify geom
    clip_ref = None
    meta_ref = None
    if is_raster(clip_geom):
        meta_ref = raster_to_metadata(clip_geom)
        clip_ref = meta_ref["extent_ogr"]
    elif is_vector(clip_geom):
        clip_ref = vector_to_reference(clip_geom)
        meta_ref = vector_to_metadata(clip_ref)
    else:
        raise ValueError(f"The clip_geom is invalid: {clip_geom}")

    remove_if_overwrite(out_path, overwrite)

    # Fast check: Does the extent of the two inputs overlap?
    # intersection = metadata["extent_ogr_geom_wgs84"].Intersection(meta_ref["extent_ogr_geom_wgs84"])
    # if intersection is None or intersection.Area() == 0.0:
    #     print("WARNING: Geometries did not intersect. Returning empty layer.")

    # TODO: Handle layer_to_clip
    out_clip_layer = None
    out_clip_ds = None
    if isinstance(clip_geom, str):
        out_clip_ds = clip_geom
    elif isinstance(clip_geom, ogr.DataSource):
        out_clip_layer = clip_geom.GetLayer()
    else:
        raise Exception("Unable to parse clip_geom.")

    warp_options = []
    if all_touch:
        warp_options.append("CUTLINE_ALL_TOUCHED=TRUE")

    # formats
    out_name = None
    out_format = None
    out_creation_options = None
    if out_path is None:
        out_name = metadata["name"]
        out_format = "MEM"
        out_creation_options = []
    else:
        out_name = out_path
        out_format = path_to_driver(out_path)
        out_creation_options = default_options(creation_options)

    # nodata
    src_nodata = metadata["nodata_value"]
    out_nodata = None
    if src_nodata is not None:
        out_nodata = src_nodata
    else:
        if dst_nodata == "infer":
            out_nodata = gdal_nodata_value_from_type(metadata["dtype_gdal_raw"])
        else:
            out_nodata = dst_nodata

    # Check if projections match, otherwise reproject target geom.
    if not metadata["projection_osr"].IsSame(meta_ref["projection_osr"]):
        clip_ref = reproject_vector(clip_ref, metadata["projection_osr"], out_path="/vsimem/clip_geom.gpkg")
    
    og_minX, og_maxY, og_maxX, og_minY = metadata["extent"]
    output_bounds = (og_minX, og_minY, og_maxX, og_maxY)

    if crop_to_geom:
        clip_meta = vector_to_metadata(clip_ref)

        if adjust_bbox:
            output_bounds = align_bbox(
                metadata["extent"],
                clip_meta["extent"],
                metadata["pixel_width"],
                metadata["pixel_height"],
            )


    clipped = gdal.Warp(
        out_name,
        ref,
        format=out_format,
        resampleAlg=translate_resample_method(resample_alg),
        targetAlignedPixels=False,
        outputBounds=output_bounds,
        xRes=metadata["pixel_width"],
        yRes=metadata["pixel_height"],
        cutlineDSName=out_clip_ds,
        cutlineLayer=out_clip_layer,
        cropToCutline=False,
        creationOptions=out_creation_options,
        warpOptions=warp_options,
        srcNodata=metadata["nodata_value"],
        dstNodata=out_nodata,
        multithread=True,
    )

    if clipped is None:
        print("WARNING: Output is None. Returning empty layer.")

    if out_path is not None:
        return out_path
    else:
        return clipped
