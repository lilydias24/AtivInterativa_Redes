# Atividade Interativa | Protocolos - Versão 26.06.26

**Disciplina:** Redes de Computadores  
**Protocolo escolhido:** MCP (Model Context Protocol)  
**Cenário:** Fazenda Inteligente - IA auxiliando o produtor rural

### 1. Descrição

O cenário simula uma **fazenda com sistema de irrigação inteligente** onde um produtor rural conversa com um assistente de inteligência artificial para tomar decisões como:

- "Preciso irrigar hoje?"
- "Quanto de água devo usar?"
- "Como está o tempo para amanhã?"

Para responder, a IA não tem os dados diretamente, é necessário consultá-los em diferentes fontes, como: um servidor de clima, um sensor de umidade do solo e um controlador de irrigação.
O protocolo MCP é o meio pelo qual essa comunicação acontece de forma padronizada.

### 2. O Protocolo MCP

O Model Context Protocol (MCP) é um protocolo aberto criado pela Anthropic em 2024 com o objetivo de padronizar a comunicação entre modelos de linguagem (LLMs) e fontes externas de dados ou ferramentas. Ele define:

- Como um "cliente MCP" (geralmente a IA) descobre quais ferramentas um servidor oferece.
- Como o cliente "invoca" essas ferramentas com parâmetros estruturados (JSON).
- Como o servidor "retorna*" os resultados de volta à IA.
- Como o transporte pode ser feito via "stdio" (processos locais) ou "HTTP com SSE" (servidores remotos).

A arquitetura segue o padrão cliente-servidor, mas voltada especificamente para a integração
de IA com o mundo externo, substituindo integrações ad-hoc e proprietárias por um contrato
de comunicação único e reusável.

### 3. Por que MCP foi o protocolo escolhido para este cenário

Em resumo: O MCP é a escolha mais alinhada ao cenário porque o problema é  multi-fonte: clima, solo e irrigação são sistemas separados que precisam ser consultados juntos. A IA precisa de descoberta dinâmica de capacidades, não de endpoints codificados. A resposta ao produtor exige síntese e raciocínio sobre dados agregados, não apenas retransmissão de valores. O protocolo foi projetado exatamente para conectar LLMs ao mundo externo de forma padronizada, segura e extensível.

Em cenários onde os sensores precisariam transmitir dados continuamente em tempo real(rastreamento ao vivo, alertas imediatos), MQTT seria a escolha complementar ideal, podendo inclusive alimentar os servidores MCP com dados atualizados. As tecnologias não são concorrentes, mas o MCP é o protocolo que unifica a camada de inteligência. 

**Motivo específico 1 : Múltiplas fontes de informação heterogêneas**

O cenário conta com três servidores completamente diferentes:

| Servidor             | Tipo de dado       | Tecnologia subjacente (hipotética)  |
|----------------------|--------------------|--------------------------------------|
| Servidor de Clima    | REST / API pública | Open-Meteo, INMET                    |
| Sensor de Umidade    | Dispositivo IoT    | Sensor capacitivo com firmware local |
| Controlador de Irrigação | Sistema local | PLC ou microcontrolador              |

Sem um protocolo padronizado, a IA precisaria de uma integração diferente para cada um. Ja com MCP, todos expõem a mesma interface, permitindo que o cliente aprende uma vez sobre MCP e consiga usar qualquer servidor sem código extra.

**Motivo específico 2 : Semântica orientada a ferramentas**

O MCP foi projetado para que a IA descubra dinamicamente quais ferramentas estão disponíveis e decida qual usar conforme a intenção da pergunta. Isso é fundamental para o cenário: a pergunta "Preciso irrigar hoje?" exige consultar clima e umidade e status de irrigação. A IA decide isso em tempo de execução, não em tempo de design.

Protocolos como HTTP poderiam ser usados, mas exigiriam que a IA conhecesse previamente a URL e o schema de cada API. O MCP inverte isso já que os servidores se descrevem, e a IA se adapta.

**Motivo específico 3 : Composição de respostas (fan-out)**

Uma única pergunta do produtor pode gerar chamadas para 2 ou 3 servidores diferentes. O MCP Client reúne todas essas respostas e a IA as sintetiza em uma única resposta coerente. Isso é chamado de padrão **fan-out com agregação**, e é algo que MQTT, HTTP puro e CoAP não oferecem nativamente, precisariam implementar essa lógica de orquestração manualmente.

**Motivo específico 4 : Comparação com os outros protocolos**

| Critério                          | MCP  | MQTT | HTTP | CoAP |
|-----------------------------------|------|------|------|------|
| Integração nativa com IA          | ✓    | ✕   | ✕   | ✕   |
| Descoberta dinâmica de ferramentas| ✓   | ✕   | ✕   | ✕   |
| Múltiplas fontes padronizadas     | ✓   | ‼   | ‼   | ✕   |
| Transporte leve (IoT)             | ‼   | ✓   | ✕   | ✓   |
| Pub/Sub (eventos contínuos)       | ✕   | ✓   | ✕   | ‼   |
| Adequado para sensores simples    | ✕   | ✓   | ‼   | ✓   |

**MQTT** seria mais adequado se o foco fosse *coleta contínua de dados dos sensores* pois é leve, eficiente e funciona bem em redes com baixa banda. Porém, ele não entende intenções.

**HTTP** permitiria consumir APIs de clima, mas cada endpoint teria um contrato diferente, sem autodescoberta nem integração semântica com a IA.

**CoAP** é ideal para dispositivos com recursos extremamente limitados, mas não possui o conceito de ferramentas compostas nem integração com modelos de linguagem.

**MCP** se destaca pois posiciona a IA como orquestradora central, capaz de descobrir serviços, combiná-los e raciocinar sobre os resultados.

**Motivo específico 5 :  Extensibilidade sem reescrita**

Caso a fazenda cresça e precise de novos sensores (pH do solo, nível de nutrientes,
câmeras de detecção de pragas), basta adicionar um novo servidor MCP. A IA descobre
automaticamente as novas ferramentas via `tools/list` e passa a usá-las. Nenhuma
alteração é necessária no assistente ou nos servidores existentes.


### 4. Arquitetura implementada

```
Produtor rural (linguagem natural)
        ↓
  Assistente IA
  (interpreta intenção e decide quais tools chamar)
        ↓
    MCP Client
    (roteia chamadas via protocolo MCP)
        ↓  ──────────────────────────────↓──────────────────────↓
  Servidor MCP      Servidor MCP           Servidor MCP
    Clima             Umidade do solo         Irrigação
  (tools: previsão,  (tools: ler_umidade,   (tools: status,
   temperatura)       histórico)             calcular_volume,
                                             ativar_irrigacao)
        ↓  ──────────────────────────────↑──────────────────────↑
  Respostas JSON retornam ao MCP Client
        ↓
  IA sintetiza e responde ao produtor
```

#### → Fluxo detalhado da pergunta "Preciso irrigar hoje?"

1. Produtor faz a pergunta em linguagem natural.
2. IA identifica que precisa de: previsão de chuva, umidade do solo e status atual
   da irrigação.
3. MCP Client chama `mcp-servidor-clima :: obter_previsao`.
4. MCP Client chama `mcp-servidor-umidade-solo :: ler_umidade`.
5. MCP Client chama `mcp-servidor-irrigacao :: status_irrigacao`.
6. IA recebe os três resultados, aplica a lógica de decisão e responde:
   *"Recomendado irrigar. Umidade do solo está em 28% e não há chuva prevista."*


### 5. O que funciona na implementação atual

A simulação cobre os seguintes pontos funcionais:

- **Arquitetura MCP completa:** cliente, 3 servidores e ferramentas independentes por servidor;
- **Descoberta dinâmica de tools:** a IA lista as capacidades disponíveis em tempo de execução via `tools/list`;
- **Fan-out com agregação:** uma única pergunta consulta múltiplos servidores em sequência e sintetiza uma resposta;
- **Lógica de decisão contextual:** a recomendação de irrigação cruza umidade do solo com previsão de chuva;
- **Dois modos de uso:** demo automático com perguntas pré-definidas e modo interativo via terminal (`-i`);
- **Sem dependências externas:** roda com Python padrão, sem instalação adicional.

### 6. Planejamentos futuros que podem ser explorados:

- **Transporte real MCP:** substituir as chamadas Python diretas por transporte via stdio ou HTTP com SSE, conforme especifica o protocolo;
- **Integração com LLM:** conectar à API do Claude para interpretação real de linguagem natural, eliminando o roteamento baseado em palavras-chave;
- **Sensores:** substituir os dados simulados por leituras reais de dispositivos IoT, usando MQTT ou CoAP como protocolo de coleta complementando o MCP na camada de sensoriamento;
- **Servidor de alertas:** notificar o produtor automaticamente em caso de umidade crítica, chuva excessiva ou falha no sistema de irrigação;
- **Histórico persistente:** banco de dados para registrar decisões, leituras e padrões de irrigação ao longo do tempo;
- **Interface web:** dashboard com visualização em tempo real dos dados da fazenda, consumindo os mesmos servidores MCP via HTTP+SSE.



> *Simulação implementada em Python no arquivo `fazenda_inteligente_mcp.py`*  
*Execução: `python fazenda_inteligente_mcp.py` (demo) ou `-i` (interativo)*
