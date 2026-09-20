"""Streamlit Community Cloud entrypoint."""

import runpy

runpy.run_module("soccer_engine.dashboard.app", run_name="__main__")
