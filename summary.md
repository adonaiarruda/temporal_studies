# temporal_studies


# Summary

Temporal is the open source runtime for managing distributed application state at scale.

# Components

![Components](imgs/Screenshot%20From%202026-04-08%2014-40-34.png)

- Workflow — a lógica de negócio principal. Pode envolver transferências bancárias, processamento de pedidos, deploy de infraestrutura, treinamento de modelos de IA, ou qualquer outra coisa. O estado completo do Workflow é durável e fault-tolerant por padrão, podendo ser recuperado, reexecutado (replay) ou pausado de qualquer ponto arbitrário. - Activities — são as partes que interagem com o mundo real: APIs que falham, usuários que demoram, dispositivos instáveis. Activities podem rodar pelo tempo necessário (com heartbeat), ser retentadas automaticamente para sempre (como policy), e ser roteadas para serviços ou processos específicos. 
- Workers — fazem polling de uma Task Queue e recebem tarefas para executar. Reportam o resultado de volta ao Service, que responde adicionando mais tarefas à fila, repetindo até o fim da execução. 
- Temporal Service — mantém um histórico detalhado de cada execução. Se o app crasha, outro Worker assume automaticamente fazendo replay desse histórico para recuperar o estado anterior ao crash, e continua de onde parou. 

# Why to use

O Temporal virou o padrão de facto para agentes de IA de longa duração porque resolve exatamente os problemas críticos de pipelines de ML e agentes:

- Pipelines de treinamento: um job que roda por horas pode retomar de onde parou se o host cair
- Agentes multi-step: um agente que chama 10 LLMs em sequência não perde progresso se uma chamada falhar
- Human-in-the-loop: o Workflow pode pausar esperando aprovação humana por dias ou semanas sem consumir recursos
- Suporte nativo a Agents, MCP e AI Pipelines — desenvolva agentes que sobrevivem ao caos do mundo real, MCP confiável e orquestre training pipelines

# Durable Execution Machanism

O segredo é Event Sourcing + Replay determinístico. O Temporal não persiste variáveis em memória — ele persiste eventos. Quando um Worker retoma um Workflow crashado, ele não carrega estado salvo: ele re-executa o código do Workflow do início, mas "injeta" os resultados já conhecidos dos eventos passados sem re-executar as Activities. O código parece estar rodando normal, mas na prática está replaying história.

Isso cria uma restrição importante: código de Workflow deve ser determinístico — sem random(), sem datetime.now(), sem I/O direto. Toda interação com o mundo externo vai em Activities.