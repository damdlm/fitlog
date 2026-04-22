# Guia de Contribuição para o FitLog

## Como Contribuir

1. **Fork o repositório**
2. **Crie uma branch** (`git checkout -b feature/nova-funcionalidade`)
3. **Faça commit das mudanças** (`git commit -m 'Adiciona nova funcionalidade'`)
4. **Push para a branch** (`git push origin feature/nova-funcionalidade`)
5. **Abra um Pull Request**

## Padrões de Código

### Python
- Use PEP 8
- Docstrings para todas as funções públicas
- Tipos com type hints

### JavaScript
- Use camelCase para variáveis e funções
- Comentários em português
- Módulos com IIFE

### Templates
- Indentação com 4 espaços
- Comentários Jinja2 quando necessário

## Estrutura de Commits

- `feat:` - Nova funcionalidade
- `fix:` - Correção de bug
- `docs:` - Documentação
- `style:` - Formatação
- `refactor:` - Refatoração
- `test:` - Testes
- `chore:` - Manutenção

## Testes

Execute os testes antes de commitar:
```bash
pytest tests/