"""FAZENDA INTELIGENTE — Simulação com Model Context Protocol (MCP)"""

import json
import random
from datetime import datetime
import sys


# ── Servidores MCP

class MCPServer:
    """Classe base de um servidor MCP: registra e executa ferramentas."""

    def __init__(self, nome: str):
        self.nome = nome
        self.tools: dict[str, dict] = {}

    def registrar_tool(self, nome: str, descricao: str, parametros: dict):
        self.tools[nome] = {"descricao": descricao, "parametros": parametros}

    def listar_tools(self) -> list[dict]:
        """Equivalente ao tools/list do protocolo MCP."""
        return [
            {"nome": k, "descricao": v["descricao"], "parametros": v["parametros"]}
            for k, v in self.tools.items()
        ]

    def chamar_tool(self, nome_tool: str, argumentos: dict) -> dict:
        """Equivalente ao tools/call do protocolo MCP."""
        if nome_tool not in self.tools:
            return {"erro": f"Tool '{nome_tool}' não encontrada em {self.nome}"}
        return self._executar(nome_tool, argumentos)

    def _executar(self, nome_tool: str, argumentos: dict) -> dict:
        raise NotImplementedError


class ServidorClima(MCPServer):
    def __init__(self):
        super().__init__("mcp-servidor-clima")
        self.registrar_tool(
            "obter_previsao",
            "Retorna previsão do tempo para a localização e data fornecidas.",
            {"localizacao": "string", "dias": "int"}
        )
        self.registrar_tool(
            "obter_temperatura_atual",
            "Retorna temperatura atual em graus Celsius.",
            {"localizacao": "string"}
        )

    def _executar(self, nome_tool: str, argumentos: dict) -> dict:
        localizacao = argumentos.get("localizacao", "Alegrete, RS")
        condicoes = ["Ensolarado", "Nublado", "Chuva leve", "Chuva forte", "Parcialmente nublado"]

        if nome_tool == "obter_previsao":
            dias = argumentos.get("dias", 1)
            return {
                "localizacao": localizacao,
                "previsao": [
                    {
                        "dia": f"+{i+1}d",
                        "condicao": random.choice(condicoes),
                        "chuva_mm": round(random.uniform(0, 25), 1),
                        "temp_max": round(random.uniform(22, 35), 1),
                        "temp_min": round(random.uniform(14, 22), 1),
                    }
                    for i in range(dias)
                ],
            }

        if nome_tool == "obter_temperatura_atual":
            return {
                "localizacao": localizacao,
                "temperatura_c": round(random.uniform(18, 38), 1),
                "sensacao_termica_c": round(random.uniform(16, 42), 1),
                "umidade_relativa_pct": round(random.uniform(30, 90), 1),
                "timestamp": datetime.now().isoformat(),
            }


class ServidorUmidadeSolo(MCPServer):
    def __init__(self):
        super().__init__("mcp-servidor-umidade-solo")
        self.registrar_tool(
            "ler_umidade",
            "Lê a umidade atual do solo em percentual para uma zona da fazenda.",
            {"zona": "string", "profundidade_cm": "int"}
        )
        self.registrar_tool(
            "historico_umidade",
            "Retorna histórico de umidade das últimas N horas.",
            {"zona": "string", "horas": "int"}
        )

    def _executar(self, nome_tool: str, argumentos: dict) -> dict:
        zona = argumentos.get("zona", "zona-1")

        if nome_tool == "ler_umidade":
            profundidade = argumentos.get("profundidade_cm", 20)
            umidade = round(random.uniform(15, 75), 1)
            status = (
                "crítico (irrigar imediatamente)" if umidade < 25
                else "baixo (irrigação recomendada)" if umidade < 40
                else "adequado" if umidade < 65
                else "saturado (não irrigar)"
            )
            return {
                "zona": zona,
                "profundidade_cm": profundidade,
                "umidade_pct": umidade,
                "status": status,
                "timestamp": datetime.now().isoformat(),
            }

        if nome_tool == "historico_umidade":
            horas = argumentos.get("horas", 6)
            return {
                "zona": zona,
                "historico": [
                    {"hora": f"-{horas - i}h", "umidade_pct": round(random.uniform(20, 70), 1)}
                    for i in range(horas)
                ],
            }


class ServidorIrrigacao(MCPServer):
    def __init__(self):
        super().__init__("mcp-servidor-irrigacao")
        self._estado: dict[str, bool] = {}
        self.registrar_tool(
            "status_irrigacao",
            "Verifica se a irrigação está ativa em uma zona.",
            {"zona": "string"}
        )
        self.registrar_tool(
            "calcular_volume",
            "Calcula o volume ideal de água (litros) com base na umidade e área.",
            {"umidade_atual_pct": "float", "area_m2": "float", "cultura": "string"}
        )
        self.registrar_tool(
            "ativar_irrigacao",
            "Ativa a irrigação em uma zona por um período definido.",
            {"zona": "string", "duracao_minutos": "int"}
        )

    def _executar(self, nome_tool: str, argumentos: dict) -> dict:
        zona = argumentos.get("zona", "zona-1")

        if nome_tool == "status_irrigacao":
            ativo = self._estado.get(zona, False)
            return {
                "zona": zona,
                "irrigacao_ativa": ativo,
                "ultima_irrigacao": "agora" if ativo else "há 6 horas",
                "vazao_l_min": round(random.uniform(80, 150), 1) if ativo else 0,
            }

        if nome_tool == "calcular_volume":
            umidade = argumentos.get("umidade_atual_pct", 30.0)
            area = argumentos.get("area_m2", 1000.0)
            cultura = argumentos.get("cultura", "soja")
            deficit = max(0, 60 - umidade)
            fator = {"soja": 1.2, "milho": 1.5, "trigo": 1.0}.get(cultura, 1.1)
            volume = round((deficit / 100) * area * 0.3 * fator, 1)
            return {
                "zona": zona,
                "cultura": cultura,
                "umidade_atual_pct": umidade,
                "volume_recomendado_litros": volume,
                "duracao_estimada_minutos": round(volume / 100),
                "observacao": "Baseado no deficit hídrico da cultura",
            }

        if nome_tool == "ativar_irrigacao":
            duracao = argumentos.get("duracao_minutos", 30)
            self._estado[zona] = True
            return {
                "zona": zona,
                "status": "Irrigação ativada com sucesso",
                "duracao_minutos": duracao,
                "inicio": datetime.now().isoformat(),
                "previsao_termino": f"em {duracao} minutos",
            }


# ── MCP Client 

class MCPClient:
    """Roteia chamadas da IA aos servidores MCP via tools/list e tools/call."""

    def __init__(self):
        self._servidores: dict[str, MCPServer] = {}

    def conectar(self, servidor: MCPServer):
        self._servidores[servidor.nome] = servidor
        print(f"  [MCP] Conectado: {servidor.nome}")

    def listar_todas_tools(self) -> list[dict]:
        return [
            {"servidor": nome, "tool": t["nome"], "descricao": t["descricao"]}
            for nome, srv in self._servidores.items()
            for t in srv.listar_tools()
        ]

    def chamar(self, servidor: str, tool: str, args: dict) -> dict:
        if servidor not in self._servidores:
            return {"erro": f"Servidor '{servidor}' não conectado."}
        print(f"  [MCP] → {servidor} :: {tool}({json.dumps(args, ensure_ascii=False)})")
        resultado = self._servidores[servidor].chamar_tool(tool, args)
        print(f"  [MCP] ← resposta recebida\n")
        return resultado


# ── Assistente IA 

class AssistenteAgricolaIA:
    """Interpreta perguntas do produtor e decide quais tools MCP consultar."""

    def __init__(self, cliente: MCPClient):
        self.cliente = cliente
        self.localizacao = "Alegrete, RS"
        self.zona = "zona-1"
        self.area_m2 = 2000.0
        self.cultura = "soja"

    def responder(self, pergunta: str) -> str:
        p = pergunta.lower()
        if any(w in p for w in ["irrigar", "irrigação", "regar"]):
            return self._recomendar_irrigacao()
        if any(w in p for w in ["tempo", "chuva", "clima", "temperatura"]):
            return self._consultar_clima()
        if any(w in p for w in ["umidade", "solo"]):
            return self._consultar_umidade()
        if any(w in p for w in ["quanto", "litros", "volume"]):
            return self._calcular_volume()
        if any(w in p for w in ["ligar", "ativar"]):
            return self._ativar_irrigacao()
        return (
            "Posso ajudar com:\n"
            "  • Previsão do tempo\n"
            "  • Umidade do solo\n"
            "  • Volume de irrigação\n"
            "  • Ativar irrigação\n"
            "  • Recomendação completa de irrigação"
        )

    def _recomendar_irrigacao(self) -> str:
        print("  [IA] Fan-out: consultando clima, umidade e status de irrigação...\n")
        clima = self.cliente.chamar(
            "mcp-servidor-clima", "obter_previsao",
            {"localizacao": self.localizacao, "dias": 2}
        )
        umidade = self.cliente.chamar(
            "mcp-servidor-umidade-solo", "ler_umidade",
            {"zona": self.zona, "profundidade_cm": 20}
        )
        irrigacao = self.cliente.chamar(
            "mcp-servidor-irrigacao", "status_irrigacao",
            {"zona": self.zona}
        )

        um_pct = umidade["umidade_pct"]
        chuva_mm = clima["previsao"][0].get("chuva_mm", 0) if clima["previsao"] else 0

        if um_pct >= 60:
            recomendacao = "Não irrigar. Solo com umidade adequada ou saturado."
        elif chuva_mm > 10:
            recomendacao = f"Aguardar. Chuva de {chuva_mm}mm prevista amanhã."
        else:
            recomendacao = "Recomendado irrigar. Umidade baixa e sem chuva prevista."

        return (
            f"═══ RECOMENDAÇÃO DE IRRIGAÇÃO ═══\n"
            f"Zona             : {self.zona}\n"
            f"Umidade do solo  : {um_pct}% ({umidade['status']})\n"
            f"Chuva prevista   : {chuva_mm}mm\n"
            f"Irrigação ativa  : {'Sim' if irrigacao['irrigacao_ativa'] else 'Não'}\n"
            f"\n{recomendacao}"
        )

    def _consultar_clima(self) -> str:
        print("  [IA] Consultando servidor de clima...\n")
        atual = self.cliente.chamar(
            "mcp-servidor-clima", "obter_temperatura_atual",
            {"localizacao": self.localizacao}
        )
        previsao = self.cliente.chamar(
            "mcp-servidor-clima", "obter_previsao",
            {"localizacao": self.localizacao, "dias": 3}
        )
        dias_str = "\n".join(
            f"  {d['dia']}: {d['condicao']}, {d['chuva_mm']}mm, {d['temp_min']}–{d['temp_max']}°C"
            for d in previsao["previsao"]
        )
        return (
            f"═══ CONDIÇÕES CLIMÁTICAS — {self.localizacao} ═══\n"
            f"Temperatura atual  : {atual['temperatura_c']}°C\n"
            f"Sensação térmica   : {atual['sensacao_termica_c']}°C\n"
            f"Umidade relativa   : {atual['umidade_relativa_pct']}%\n"
            f"\nPrevisão próximos dias:\n{dias_str}"
        )

    def _consultar_umidade(self) -> str:
        print("  [IA] Consultando servidor de umidade do solo...\n")
        atual = self.cliente.chamar(
            "mcp-servidor-umidade-solo", "ler_umidade",
            {"zona": self.zona, "profundidade_cm": 20}
        )
        historico = self.cliente.chamar(
            "mcp-servidor-umidade-solo", "historico_umidade",
            {"zona": self.zona, "horas": 6}
        )
        hist_str = "  |  ".join(
            f"{h['hora']}: {h['umidade_pct']}%" for h in historico["historico"]
        )
        return (
            f"═══ UMIDADE DO SOLO — {self.zona} ═══\n"
            f"Umidade atual : {atual['umidade_pct']}%\n"
            f"Status        : {atual['status']}\n"
            f"Profundidade  : {atual['profundidade_cm']}cm\n"
            f"\nHistórico (últimas 6h):\n  {hist_str}"
        )

    def _calcular_volume(self) -> str:
        print("  [IA] Calculando volume de água necessário...\n")
        umidade = self.cliente.chamar(
            "mcp-servidor-umidade-solo", "ler_umidade",
            {"zona": self.zona, "profundidade_cm": 20}
        )
        volume = self.cliente.chamar(
            "mcp-servidor-irrigacao", "calcular_volume",
            {
                "zona": self.zona,
                "umidade_atual_pct": umidade["umidade_pct"],
                "area_m2": self.area_m2,
                "cultura": self.cultura,
            }
        )
        return (
            f"═══ VOLUME DE IRRIGAÇÃO RECOMENDADO ═══\n"
            f"Zona          : {self.zona}\n"
            f"Cultura       : {self.cultura}\n"
            f"Área          : {self.area_m2}m²\n"
            f"Umidade atual : {umidade['umidade_pct']}%\n"
            f"Volume ideal  : {volume['volume_recomendado_litros']} litros\n"
            f"Duração est.  : {volume['duracao_estimada_minutos']} minutos\n"
            f"Obs.          : {volume['observacao']}"
        )

    def _ativar_irrigacao(self) -> str:
        print("  [IA] Calculando duração e ativando irrigação...\n")
        volume = self.cliente.chamar(
            "mcp-servidor-irrigacao", "calcular_volume",
            {"zona": self.zona, "umidade_atual_pct": 30.0, "area_m2": self.area_m2, "cultura": self.cultura}
        )
        resultado = self.cliente.chamar(
            "mcp-servidor-irrigacao", "ativar_irrigacao",
            {"zona": self.zona, "duracao_minutos": volume["duracao_estimada_minutos"]}
        )
        return (
            f"═══ IRRIGAÇÃO ATIVADA ═══\n"
            f"{resultado['status']}\n"
            f"Zona          : {resultado['zona']}\n"
            f"Duração       : {resultado['duracao_minutos']} minutos\n"
            f"Início        : {resultado['inicio']}\n"
            f"Previsão fim  : {resultado['previsao_termino']}"
        )


# ── Interface de simulação 

def linha(titulo: str = ""):
    sep = "─" * 60
    print(f"\n{sep}\n  {titulo}\n{sep}" if titulo else f"\n{sep}")


def inicializar_sistema() -> AssistenteAgricolaIA:
    client = MCPClient()
    client.conectar(ServidorClima())
    client.conectar(ServidorUmidadeSolo())
    client.conectar(ServidorIrrigacao())
    return AssistenteAgricolaIA(client), client


def rodar_demo():
    linha("FAZENDA INTELIGENTE — Simulação MCP")
    print("\nInicializando servidores MCP...")
    assistente, client = inicializar_sistema()

    linha("Ferramentas disponíveis (tools/list)")
    for t in client.listar_todas_tools():
        print(f"  [{t['servidor']}] {t['tool']}: {t['descricao']}")

    perguntas = [
        "Preciso irrigar hoje?",
        "Como está o tempo para os próximos dias?",
        "Qual a umidade do solo agora?",
        "Quantos litros de água devo usar?",
        "Pode ligar a irrigação?",
    ]

    for pergunta in perguntas:
        linha(f"Produtor: {pergunta}")
        print(f"\n Assistente IA:\n\n{assistente.responder(pergunta)}\n")

    linha("FIM DA SIMULAÇÃO")
    print("\nTodos os servidores MCP foram consultados com sucesso.\n")


def rodar_interativo():
    linha("MODO INTERATIVO — Fazenda Inteligente MCP")
    print("\nInicializando...\n")
    assistente, _ = inicializar_sistema()
    print("Sistema pronto. Digite sua pergunta (ou 'sair' para encerrar).\n")

    while True:
        try:
            pergunta = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not pergunta:
            continue
        if pergunta.lower() in ("sair", "exit", "quit"):
            print("Encerrando. Até logo!")
            break
        print(f"\nAssistente:\n\n{assistente.responder(pergunta)}\n")


if __name__ == "__main__":
    if "--interativo" in sys.argv or "-i" in sys.argv:
        rodar_interativo()
    else:
        rodar_demo()
