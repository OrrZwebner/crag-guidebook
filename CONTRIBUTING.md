# Contributing

Run the tests with `python3 tests/run_tests.py` (standard library only; the PDF round trip
runs when WeasyPrint and PyMuPDF are installed).

The values in `tests/expected.json` were derived by hand from the synthetic crag in
`crag-guidebook/examples/`, independently of the scripts. Do not update them to match new
output: if a value moves, the code is wrong until proven otherwise.
