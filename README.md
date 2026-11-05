# P2: MCP server da reforma tributária

MCP server que busca dispositivos da reforma tributária (EC 132/2023) e responde
sempre com o dispositivo citado e a data a partir da qual ele produz efeitos.
Projeto de estudo do roadmap "Engenharia de Software com Agentes de IA" (Fase 2).

## Estado

Em construção, um passo por vez. Cada passo tem uma nota em `docs/steps/`.

## Como rodar os testes

    uv sync
    uv run pytest

## Dados

Só normas públicas (texto oficial do Planalto). Nenhum dado de contribuinte,
nem em testes.

## Decisões e limites

Ver `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md`.
