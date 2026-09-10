# Upstream draft — omnigent: unsupported per-model effort fails silently

Filed at: omnigent-ai/omnigent (kzarzycki/omnigent is a fork with issues disabled).

---

**Title:** [Bug] codex-native: an effort the model doesn't offer kills the turn with no error

**Body:**

Set `reasoning_effort: minimal` on a `codex-native` session running
`gpt-6-astra`: the PATCH succeeds, a GET reports it back, and then the first
turn ends `status: failed` with no output and zero token usage. Nothing says
why. The same brief at `low` works.

astra has no `minimal`. `CODEX_NATIVE_EFFORTS` deliberately carries the full
ladder because codex is the per-model authority on levels
(`omnigent/util/reasoning_effort.py`) — that part is fine. The gap is that when
codex rejects the pairing, nothing surfaces it: the caller sees a bare failed
turn and no error, which reads as a harness fault. I went looking at the
harness first.

Either surface codex's rejection as the turn error, or gate the effort by the
model's advertised levels from `model/list`.

Related from the other end of the same ladder gap: #6555, #6553, #5360 all
cover efforts the model supports but omnigent rejects or clamps. This is the
reverse — accepted by omnigent, unsupported by the model.

Reproduced twice on `main` @ `8627eb9f` with codex-cli 0.153.4, with a working
`low` run in between. Only tested `codex-native` + `minimal`.

Sessions, if server-side logs can be pulled for the actual rejection:
`71c75c4f33de4d369ae99a8adbedfd5a` (minimal, failed), `eb953ffc5026486baef8ead00b4683b3`
(minimal, failed), `723e2c2ef06547a896f125db0db930af` (low, succeeded).
