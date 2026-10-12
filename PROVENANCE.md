# Origem e direitos

## Conteúdo original

- `install.sh`, `scripts/`, `tests/`, documentação e workflow: implementação original preparada para esta coleção em 12/10/2026.
- `skills/review-checklist/SKILL.md`: exemplo original, criado para esta coleção; não copiado de uma skill externa.
- As referências oficiais no README orientaram a compatibilidade de formato e caminhos. Não são fontes de skills redistribuídas.
- Licença do conteúdo original: **pendente de escolha pelo mantenedor**. Não há atribuição automática de MIT ou outra licença.

## Política para futuras skills de terceiros

Antes de incorporar conteúdo, registre aqui:

- Nome da skill e diretório local.
- URL exata da origem, autor e commit/tag consultado.
- Licença original e caminho da cópia integral dos avisos exigidos.
- Data de incorporação e modificações realizadas.
- Eventuais restrições adicionais ou incompatibilidades.

Conserve atribuições e avisos; não rebatize trabalho de terceiros como original. Se a licença for ausente, incompatível ou ambígua, mantenha apenas um link descritivo até obter permissão verificável. Hashes identificam os arquivos distribuídos, mas não substituem licença, proveniência ou revisão de segurança.

## Matt Pocock: grill-me e grilling

- Autor: Matt Pocock, repositório [mattpocock/skills](https://github.com/mattpocock/skills).
- Incorporado em 12/10/2026 a partir do commit fixo `49dd158d1076134a641b33efb035946536778336` (HEAD de `main` consultado nessa data).
- [grill-me upstream](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/productivity/grill-me/SKILL.md) → `skills/grill-me/SKILL.md`.
- [grilling upstream](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/productivity/grilling/SKILL.md) → `skills/grilling/SKILL.md`, dependência real do wrapper.
- Os arquivos `agents/openai.yaml` de ambas as pastas foram copiados sem alterações do mesmo commit.
- Licença: [MIT upstream](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/LICENSE), copyright (c) 2026 Matt Pocock. Cópias integrais distribuídas em `skills/grill-me/LICENSE` e `skills/grilling/LICENSE`, incluídas pelo instalador mesmo na instalação individual.
- Alterações locais: o wrapper usa `Skill` quando disponível, com fallback para leitura do `../grilling/SKILL.md` e erro claro se ausente. A primitiva permite pesquisa direta com ferramentas somente de leitura quando o agente não dispõe de subagentes. O restante das instruções de entrevista foi preservado: rodadas da fronteira de decisões, recomendações, respostas do usuário e confirmação final antes de agir.
- Revisão: conteúdo tratado como dados, sem execução durante importação/instalação. Não contém scripts executáveis, credenciais ou endpoints de exfiltração. Consultas e qualquer ação sugerida pela skill continuam sujeitas às ferramentas, permissões e aprovações do agente. Não há garantia de comportamento do modelo; teste interativo nos agentes ainda é necessário.
- Essa licença cobre os arquivos externos e suas adaptações; não relicencia o conteúdo original da coleção.
