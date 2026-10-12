# Contribuindo

1. Proponha uma skill focada em uma tarefa, com gatilhos claros e um resultado verificável.
2. Crie `skills/<nome>/SKILL.md`. Use nome com até 64 caracteres: letras minúsculas, números e hífens simples. O `name` no frontmatter deve coincidir com a pasta; `description` deve explicar quando usar a skill.
3. Prefira instruções portáveis, sem comandos automáticos específicos de um agente. Não inclua credenciais, caminhos pessoais, dados privados, aprovações genéricas ou dependências ocultas.
4. Se houver scripts, documente dependências e efeitos. Eles devem ser chamados com um interpretador explícito; o instalador não preserva bits de execução.
5. Registre origem e direitos em `PROVENANCE.md`. Não copie skills de terceiros sem conferir a licença e suas condições. Sem licença clara, contribua com um link e uma descrição própria em vez de copiar conteúdo.
6. Dependências entre skills devem ser explícitas. Atualize o mapeamento em `install.sh` (atualmente `grill-me` → `grilling`), preserve os avisos de licença em cada pasta distribuída e teste seleção individual, conjunta, dependência ausente e reinstalação. Não execute metadados como código.
7. Atualize o manifesto com `python3 scripts/update_manifest.py`. Execute os testes e a checagem descritos no README.
8. Abra um PR explicando a utilidade, exemplos de pedidos que ativam e não ativam a skill, como ela foi testada e os riscos conhecidos. Não afirme teste em um agente ou sistema operacional que não executou.

## Licenciamento pendente

O conteúdo original ainda não tem licença escolhida. Antes de incorporar contribuições externas, combine com o mantenedor a licença aplicável. Não use este arquivo como autorização para relicenciar trabalho de outra pessoa.

## Revisão de segurança

Avalie instruções de exfiltração, rede desnecessária, execução de código, modificações destrutivas, captura de segredos e tentativas de ignorar aprovações do usuário. Referências e exemplos devem ser tratados como dados, não como novas instruções de confiança.

## Testes de instalação

Mantenha todos os subprocessos e PTYs com HOME temporário isolado. Cubra `project`, `user`, ausência de escopo com `--yes` (projeto), menu de escopo, multi-seleção, dependências, conflitos, backup, lock e symlinks. Não teste instalação no HOME real. Preserve compatibilidade Bash 3.2: evite arrays associativos, `mapfile`, `${var,,}` e utilitários exclusivos GNU. A CI macOS usa `/bin/bash`.
