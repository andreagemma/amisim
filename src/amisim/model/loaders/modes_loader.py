from ..modes import Modes, ModeType
from ..base_model import InputType
from gataframe import Engine



class ModesLoader:
    def __init__(self):
        self._modes: ModeType | None = None

    @property
    def modes(self) -> ModeType | None:
        return self._modes
    
    @classmethod
    def read(cls, engine: Engine, kw_modes: InputType) -> "ModesLoader":
        this = cls()
        ret = Modes.read(engine, params=kw_modes)
        if ret is not None and ret.df is not None:
            modes = ret.df.set_index("code").to_dict(orient="index")
            modes = {str(k): v for k, v in modes.items()}
            this._modes = modes # type: ignore
        else:
            raise ValueError("Failed to read modes")

        return this

