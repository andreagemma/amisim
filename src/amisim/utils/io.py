import re
from gataframe import GataFrame, Engine
from pandas import DataFrame
from geopandas import GeoDataFrame
from collections import defaultdict

def read_source(engine: Engine,
                source: str | DataFrame,
                format: str | None = None,
                mapping: dict[str, str] | None = None,
                pre_filter: str | None = None,
                filter: str | None = None,
                dtype: dict[str, str ] | None = None,
                geometry_column: str | None = None,
                crs: str | None = None,
                limit: int | None = None,
                pre_limit: int | None = None,
                ) -> DataFrame | GeoDataFrame:

    gf: GataFrame | None = engine.read(
        source=source,
        format=format,
        limit=limit,
        pre_filter=pre_filter,
        pre_limit=pre_limit
    )

    if gf is None:
        raise ValueError(f"Failed to read source: {source}")
    
    if mapping is not None:
        inverse_mapping = defaultdict(list)
        source_cols_or_expressions = list(mapping.values())
        for target_col, source_col in mapping.items():
            inverse_mapping[source_col].append(target_col)

        # estraggo le colonne sempliciemente calcoate controllando con le espressioni regolari quali sono composte da
        # caratteri ammessi per il nome delle colonne anche gli doppi apici
        regular_columns_pattern = r'^"?[a-zA-Z_][a-zA-Z0-9_]*"?$'        
        regular_columns = [col for col in source_cols_or_expressions if re.match(regular_columns_pattern, col)]
        calculated_columns = [col for col in source_cols_or_expressions if col not in regular_columns]
        _temp_mapping = {f"__tmp_{i}__": col for i, col in enumerate(calculated_columns)}

        # creeo le nuove colonne calcolate con nomi temporanei
        if _temp_mapping:
            gf = gf.withColumn(_temp_mapping)
            # aggiorno la mappatura inversa con i nomi temporanei
            for source_col, target_cols in inverse_mapping.items():
                for i, target_col in enumerate(target_cols):
                    if target_col in _temp_mapping:
                        inverse_mapping[source_col][i] = f"__tmp_{list(_temp_mapping.keys()).index(target_col)}__"

        # rinomino le colonne regolari con i nomi target
        if regular_columns:
            to_rename = {}
            new_names = {col: inverse_mapping[col] for col in regular_columns}
            for target_col, source_cols in new_names.items():
                for source_col in source_cols:
                    if source_col in gf.columns:
                        to_rename[source_col] = target_col
            gf = gf.withColumn(to_rename)

        # rinomino le colonne temporanee con i nomi target
        if _temp_mapping:
            to_rename = {}
            temp_rename = {f"__tmp_{i}__": inverse_mapping[col] for i, col in enumerate(calculated_columns)}
            for target_col, source_cols in temp_rename.items():
                for i, source_col in enumerate(source_cols):
                    if target_col in gf.columns:
                        to_rename[source_col] = target_col
            gf = gf.withColumn(to_rename)
            gf = gf.dropColumn(list(_temp_mapping.keys()))    
            if gf is None:
                raise ValueError(f"Failed to rename temporary columns in GataFrame")
    
    if dtype is not None:
        gf = gf.as_type(dict(dtype))

    if filter is not None:
        gf = gf.filter(filter)

    df = gf.toPandasOrGeoPandas(geometry=geometry_column, crs=crs)

    if df is None:
        raise ValueError(f"Failed to convert GataFrame to DataFrame/GeoDataFrame")
    return df
