"""Teste mínimo do passo 00: o pacote existe e é importável.

Parece trivial, mas confirma três coisas de uma vez: o layout src/ está
certo, o uv instalou o pacote em modo editável e o pytest acha os testes.
"""

import taxlaw


def test_package_has_version():
    # A versão vive num lugar só (__init__.py) para não divergir do pyproject.
    assert taxlaw.__version__ == "0.1.0"
