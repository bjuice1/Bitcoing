"""Tests for CLI commands."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from click.testing import CliRunner
from main import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_cli_help(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Bitcoin Cycle Monitor" in result.output


def test_cli_version(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "1.0.0" in result.output


def test_monitor_help(runner):
    result = runner.invoke(cli, ["monitor", "--help"])
    assert result.exit_code == 0
    assert "fetch" in result.output
    assert "backfill" in result.output
    assert "status" in result.output
    assert "history" in result.output


def test_dca_help(runner):
    result = runner.invoke(cli, ["dca", "--help"])
    assert result.exit_code == 0
    assert "simulate" in result.output
    assert "compare" in result.output
    assert "project" in result.output
    assert "portfolio" in result.output


def test_alerts_help(runner):
    result = runner.invoke(cli, ["alerts", "--help"])
    assert result.exit_code == 0
    assert "check" in result.output
    assert "test" in result.output
    assert "history" in result.output
    assert "rules" in result.output


def test_dashboard_help(runner):
    result = runner.invoke(cli, ["dashboard", "--help"])
    assert result.exit_code == 0
    assert "refresh" in result.output


def test_report_help(runner):
    result = runner.invoke(cli, ["report", "--help"])
    assert result.exit_code == 0
    assert "output" in result.output


def test_export_help(runner):
    result = runner.invoke(cli, ["export", "--help"])
    assert result.exit_code == 0
    assert "format" in result.output
    assert "days" in result.output


def test_setup_help(runner):
    result = runner.invoke(cli, ["setup", "--help"])
    assert result.exit_code == 0


def test_quick_help(runner):
    result = runner.invoke(cli, ["quick", "--help"])
    assert result.exit_code == 0


def test_cycle_help(runner):
    result = runner.invoke(cli, ["cycle", "--help"])
    assert result.exit_code == 0


def test_portfolio_help(runner):
    result = runner.invoke(cli, ["dca", "portfolio", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output
    assert "buy" in result.output
    assert "status" in result.output
    assert "list" in result.output
