"""
Testes para o comportamento de logging estruturado do orquestrador (src/main.py).

Ao contrário dos testes em tests/transform/, estes não dependem de Postgres:
os passos de leitura/carga são mockados via monkeypatch, e o log é
redirecionado para um arquivo temporário. O foco aqui é o comportamento de
orquestração (contagens, etapa da falha, duração, resiliência do log),
não a lógica das views.
"""

from __future__ import annotations

import json

import pytest

from src import main as main_module


@pytest.fixture(autouse=True)
def _log_path_temporario(tmp_path, monkeypatch):
    caminho = tmp_path / "execucoes.jsonl"
    monkeypatch.setattr(main_module, "LOG_PATH", caminho)
    return caminho


def _ler_ultima_linha(caminho) -> dict:
    linhas = caminho.read_text(encoding="utf-8").strip().splitlines()
    return json.loads(linhas[-1])


def test_execucao_com_sucesso_registra_status_e_contagens(monkeypatch, _log_path_temporario):
    monkeypatch.setattr(main_module, "read_motoristas", lambda: [{"id": "1"}, {"id": "2"}])
    monkeypatch.setattr(main_module, "read_eventos", lambda: [{"event_id": "e1"}])
    monkeypatch.setattr(main_module, "read_de_para_regional", lambda: [])
    monkeypatch.setattr(main_module, "get_engine", lambda: object())
    monkeypatch.setattr(main_module, "load_motoristas", lambda engine, registros: len(registros))
    monkeypatch.setattr(main_module, "load_eventos", lambda engine, registros: len(registros))
    monkeypatch.setattr(main_module, "load_de_para_regional", lambda engine, registros: len(registros))

    main_module.main()

    registro = _ler_ultima_linha(_log_path_temporario)
    assert registro["status"] == "sucesso"
    assert registro["motoristas_processados"] == 2
    assert registro["eventos_processados"] == 1
    assert registro["de_para_processados"] == 0
    assert registro["etapa_falha"] is None
    assert registro["erro"] is None
    assert registro["duracao_segundos"] >= 0


def test_falha_na_carga_de_eventos_registra_etapa_e_contagens_parciais(monkeypatch, _log_path_temporario):
    monkeypatch.setattr(main_module, "read_motoristas", lambda: [{"id": "1"}])
    monkeypatch.setattr(main_module, "read_eventos", lambda: [{"event_id": "e1"}])
    monkeypatch.setattr(main_module, "read_de_para_regional", lambda: [])
    monkeypatch.setattr(main_module, "get_engine", lambda: object())
    monkeypatch.setattr(main_module, "load_motoristas", lambda engine, registros: len(registros))

    def _falha_carga_eventos(engine, registros):
        raise RuntimeError("conexão perdida durante carga de eventos")

    monkeypatch.setattr(main_module, "load_eventos", _falha_carga_eventos)

    with pytest.raises(RuntimeError, match="conexão perdida"):
        main_module.main()

    registro = _ler_ultima_linha(_log_path_temporario)
    assert registro["status"] == "falha"
    assert registro["etapa_falha"] == "carga_eventos"
    assert registro["motoristas_processados"] == 1
    assert registro["eventos_processados"] is None
    assert "conexão perdida" in registro["erro"]


def test_falha_ao_escrever_log_nao_esconde_erro_original(monkeypatch, _log_path_temporario):
    def _falha_leitura():
        raise RuntimeError("fonte indisponível")

    monkeypatch.setattr(main_module, "read_motoristas", _falha_leitura)

    def _registrar_com_falha(*args, **kwargs):
        raise OSError("disco cheio - não foi possível escrever o log")

    monkeypatch.setattr(main_module, "_registrar_execucao", _registrar_com_falha)

    with pytest.raises(RuntimeError, match="fonte indisponível"):
        main_module.main()


def test_falha_ao_escrever_log_apos_sucesso_nao_interrompe_execucao(monkeypatch, capsys):
    monkeypatch.setattr(main_module, "read_motoristas", lambda: [{"id": "1"}])
    monkeypatch.setattr(main_module, "read_eventos", lambda: [{"event_id": "e1"}])
    monkeypatch.setattr(main_module, "read_de_para_regional", lambda: [])
    monkeypatch.setattr(main_module, "get_engine", lambda: object())
    monkeypatch.setattr(main_module, "load_motoristas", lambda engine, registros: len(registros))
    monkeypatch.setattr(main_module, "load_eventos", lambda engine, registros: len(registros))
    monkeypatch.setattr(main_module, "load_de_para_regional", lambda engine, registros: len(registros))

    def _registrar_com_falha(*args, **kwargs):
        raise OSError("disco cheio - não foi possível escrever o log")

    monkeypatch.setattr(main_module, "_registrar_execucao", _registrar_com_falha)

    main_module.main()

    saida_erro = capsys.readouterr().err
    assert "AVISO" in saida_erro
    assert "disco cheio" in saida_erro
