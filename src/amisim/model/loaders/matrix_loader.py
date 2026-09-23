from ..base_model import InputType, InputParameters
from gataframe import Engine
from ..matrix import Matrix
from ..modes import ModeType
from matrix import MatrixODT, Timestamp, LabelsInput


class MatrixLoader:
    def __init__(self):
        self._matrices: dict[str, MatrixODT] = {}
        self._matrix_eq: MatrixODT | None = None
        self._modes: ModeType = None

    @property
    def matrices(self) -> dict[str, MatrixODT]:
        return self._matrices

    @property
    def matrix_eq(self) -> MatrixODT | None:
        return self._matrix_eq

    @classmethod
    def read(
        cls,
        engine: Engine,
        modes: ModeType,
        centroids: LabelsInput,
        timestamps: list[Timestamp],
        kws_matrices: list[dict[str, InputType]],
    ) -> "MatrixLoader":
        loader = cls()
        loader._modes = modes
        for kw_matrix in kws_matrices:
            mode = kw_matrix.get("mode")
            if mode is None:
                raise ValueError("Mode must be specified in kws_matrices.")
            mode = str(mode)
            loader._read(
                engine, kw_matrix=kw_matrix.get("matrices"), centroids=centroids, timestamps=timestamps, mode=mode
            )
        loader._matrix_eq = loader._calc_matrix_eq(modes)
        return loader

    def _calc_matrix_eq(self, modes: ModeType) -> MatrixODT:
        ret: MatrixODT | None = None
        if not self._matrices:
            raise ValueError("No matrices loaded.")
        if modes is None:
            raise ValueError("Modes must be specified.")
        for key, mat in self._matrices.items():
            eq_factor = modes.get(key, {}).get("eq_factor", 1)
            if key in modes:
                if ret is None:
                    ret = mat * eq_factor
                else:
                    ret = ret + mat * eq_factor
        if ret is None:
            raise ValueError("No matching matrices found.")
        return ret

    def _read(
        self, engine: Engine, kw_matrix: InputType, centroids: LabelsInput, timestamps: list[Timestamp], mode: str = "c"
    ) -> "MatrixLoader":
        if isinstance(kw_matrix, list):
            ret = MatrixODT(rows=centroids, cols=centroids, timestamps=timestamps, init=0.0)
            for item in kw_matrix:
                if isinstance(item, dict) and "scalar" in item:
                    scalar = item["scalar"]
                    operation = item.get("operation", "+")
                    if operation == "+":
                        ret = ret + scalar
                    elif operation == "-":
                        ret = ret - scalar
                    elif operation == "/":
                        ret = ret / scalar
                    elif operation == "*":
                        ret = ret * scalar
                    else:
                        raise ValueError(f"Unsupported operation: {operation}")
                else:
                    if timestamps:
                        first_timestamp = timestamps[0]
                        last_timestamp = timestamps[-1]
                        if first_timestamp > last_timestamp:
                            additional_filter = [
                                f"""(timestamp >=0 AND timestamp < {last_timestamp}) OR 
                                (timestamp >= {first_timestamp} AND timestamp < 1440)"""
                            ]
                        else:
                            additional_filter = [f"timestamp >= {first_timestamp} AND timestamp < {last_timestamp}"]
                    else:
                        additional_filter = None
                    bm = Matrix.read(engine, params=item, additional_filters=additional_filter)
                    if bm is None or bm.df is None:
                        raise ValueError("Failed to read matrix from item.")
                    od = MatrixODT.read_df(rows=centroids, cols=centroids, timestamps=timestamps, df=bm.df)

                    operation = "+"
                    if isinstance(item, dict) and "operation" in item:
                        operation = item.get("operation", "+")
                    elif isinstance(item, InputParameters):
                        operation = item.operation or "+"
                    if operation == "+":
                        ret = ret + od
                    elif operation == "-":
                        ret = ret - od
                    elif operation == "/":
                        ret = ret / od
                    elif operation == "*":
                        ret = ret * od
                    else:
                        raise ValueError(f"Unsupported operation: {operation}")
        else:
            bm = Matrix.read(engine, params=kw_matrix)
            if bm is None or bm.df is None:
                raise ValueError("Failed to read matrix from item.")
            ret = MatrixODT.read_df(rows=centroids, cols=centroids, timestamps=timestamps, df=bm.df)
        self._matrices[mode] = ret
        return self
