# Canonical cleanup observations

These three files are exact Git bytes from the native owner's test-only commit
`63e9890b03b4e521f002dc2415673f3c11ef6c9d`, based on accepted shared
`8062eda22ea4fe9c333798be8397ce7fa4f6f2ee`. The manifest binds both the original
fixture and the supplied successor. The shared product pin is unchanged.

`verify_native_boundary.py` creates a separate fixture copy under
`qualification-fixtures/native-boundary`, validates the baseline and successor
hashes, and runs the observer's pure checks alongside the actual packaged ABI
cases. It preserves the shared checkout and package. CI retains the fixture
provenance, raw cleanup observations, and the original test verdict.

The original Windows ARM WinError32 file holder is unknown. These observations
add no cleanup retry, wait, kill, handle ownership, DLL unload, or timeout change.
Directory cleanup failure remains fatal; a passing later run does not establish
the original cause.
