import os
import inspect

_currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))


def _load_survey_data() -> str:
    with open(f"{_currentdir}/moon_survey_input_2.txt", "r", encoding="utf-8") as f:
        return f.read()


_survey_data = _load_survey_data()


def survey_data() -> str:
    return _survey_data
