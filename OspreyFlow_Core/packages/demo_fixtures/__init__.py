"""The synthetic demo datasets, generated in code.

Fixture Corp, the HMP fixture, the CDR and seizure-record fixtures and the scenario cohorts.
They are part of the product (the seeds call them), so they live here and not in the test tree;
the tests import them from here (`spec/06_DECISIONS.md` ADR-054). Everything is generated from a
fixed seed, nothing is a real dataset, and no dataset is stored in this package.
"""
