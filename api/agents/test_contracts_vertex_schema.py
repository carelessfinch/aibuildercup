"""Every contract must survive google-genai's Vertex response-schema conversion.

Cloud Run regression (2026-10-17): ``gt=`` (exclusiveMinimum) and tuple
fields (prefixItems) passed the unit tests but crashed the first live
LlmAgent call, because Vertex's ``Schema`` model forbids those keywords.
"""

import inspect
from types import SimpleNamespace

import pytest
from google.genai import _transformers
from pydantic import BaseModel, ValidationError

from agents.contracts import models

CONTRACTS = [
    obj
    for _, obj in inspect.getmembers(models, inspect.isclass)
    if issubclass(obj, BaseModel) and obj.__module__ == models.__name__
]
VERTEX_CLIENT = SimpleNamespace(vertexai=True)


@pytest.mark.parametrize("model", CONTRACTS, ids=lambda m: m.__name__)
def test_contract_converts_to_vertex_schema(model):
    assert _transformers.t_schema(VERTEX_CLIENT, model) is not None


def test_power_coupling_eff_still_rejects_zero():
    with pytest.raises(ValidationError):
        models.OperatingPoint(power_W=100, pressure_mTorr=10, power_coupling_eff=0.0)


def test_bounds_must_be_a_pair():
    with pytest.raises(ValidationError):
        models.UncertainParameter(name="x", bounds=[1.0])
