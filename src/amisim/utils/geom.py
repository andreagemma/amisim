from shapely import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon, remove_repeated_points

__all__ = ["ST_Multi", "ST_MultiLinestring_to_LineString"]


def ST_Multi(geom):
    if isinstance(geom, Point):
        return MultiPoint([geom])
    if isinstance(geom, LineString):
        return MultiLineString([geom])
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiLineString):
        return geom
    if isinstance(geom, MultiPoint):
        return geom
    if isinstance(geom, MultiPolygon):
        return geom
    raise ValueError(f"Cannot convert {type(geom)} to Multi*")


def ST_MultiLinestring_to_LineString(multi_line: MultiLineString | LineString | None, get_only_first=False):
    if multi_line is None:
        return None
    if isinstance(multi_line, LineString):
        return multi_line

    if not isinstance(multi_line, MultiLineString):
        raise ValueError(f"Expected MultiLineString, got {type(multi_line)}")

    if get_only_first:
        if len(multi_line.coords) == 0:
            return LineString()
        return remove_repeated_points(LineString(multi_line.geoms[0].coords))

    # Extract all coordinates from the MultiLineString
    all_coords = []
    for line in multi_line.geoms:
        all_coords.extend(line.coords)

    # Create a new LineString with the concatenated coordinates
    ret = LineString(all_coords)
    ret = remove_repeated_points(ret)
    return ret
