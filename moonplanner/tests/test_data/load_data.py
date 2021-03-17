import inspect
import os

_currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))


def _load_survey_data() -> str:
    survey_data = dict()
    with open(f"{_currentdir}/moon_survey_input_2.txt", "r", encoding="utf-8") as f:
        survey_data[2] = f.read()

    with open(f"{_currentdir}/moon_survey_input_3.txt", "r", encoding="utf-8") as f:
        survey_data[3] = f.read()

    return survey_data


_survey_data = _load_survey_data()


def survey_data() -> str:
    return _survey_data
