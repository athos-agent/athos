# Contribuir

*English: [CONTRIBUTING.md](CONTRIBUTING.md)*

Gracias por querer mejorar Athos. Todo lo que aportes se publica bajo la Apache License 2.0, igual que el resto del
proyecto. Para compartir una forma de trabajar con la galería en vez de código, mirá
[gallery/CONTRIBUIR.md](gallery/CONTRIBUIR.md).

## Firmá cada commit

Usamos el [Developer Certificate of Origin 1.1](https://developercertificate.org/): cada commit de alguien de fuera del
proyecto lleva una línea que dice que escribiste el cambio, o que de otro modo tenés derecho a enviarlo:

```
Signed-off-by: Ada Lovelace <ada@example.com>
```

Commiteá con `git commit -s` y git escribe esa línea con tu nombre y tu email. Un pull request con algún commit sin esa
línea no se puede mergear.

## De la idea al pull request

1. Para cualquier cosa más allá de un arreglo chico, abrí primero un issue, así acordamos el enfoque.
2. Hacé un fork del repositorio y hacé tu cambio en una rama propia.
3. Que cada commit tenga una sola capacidad, con sus tests en el mismo commit.
4. Antes de abrir el pull request, corré los tests y dejá que pase el hook de pre-commit de gitleaks:
   - Python: `HOME=$(mktemp -d) python3 -m unittest discover -s tests -t .` (un home descartable, para que nunca se
     toque tu propio `~/.athos`)
   - el módulo de hooks de Claude Code: `claude plugin test .`

## Los datos del usuario se quedan en su máquina

Athos no manda nada fuera de la máquina de una persona salvo que lo pida explícitamente. La telemetría, los registros
remotos y las llamadas de red nuevas necesitan un issue y una discusión antes de cualquier código.
