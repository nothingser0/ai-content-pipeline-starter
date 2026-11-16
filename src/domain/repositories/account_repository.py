"""
Account repository
Loads and manages account configurations
"""

import json
from pathlib import Path
from typing import Optional

from domain.models import Account
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class AccountRepository:
    """Repository for account configurations"""

    def __init__(self, accounts_dir: Optional[Path] = None) -> None:
        if accounts_dir is None:
            # Default to project root / accounts
            self.accounts_dir = Path(__file__).parent.parent.parent.parent / "accounts"
        else:
            self.accounts_dir = accounts_dir

        if not self.accounts_dir.exists():
            raise FileNotFoundError(
                f"Accounts directory not found: {self.accounts_dir}"
            )

    def get_account(self, account_id: str) -> Account:
        """
        Load account configuration

        Args:
            account_id: Account ID (e.g., "01-ai-automation")

        Returns:
            Account domain model

        Raises:
            FileNotFoundError: If account config not found
            ValueError: If config is invalid
        """
        account_dir = self.accounts_dir / account_id
        config_file = account_dir / "config.json"

        if not config_file.exists():
            raise FileNotFoundError(f"Account config not found: {config_file}")

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            account = Account.from_dict(config_data)
            logger.debug(f"Loaded account: {account_id}")
            return account

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {config_file}: {e}")
        except KeyError as e:
            raise ValueError(f"Missing required field in {config_file}: {e}")

    def get_account_dict(self, account_id: str) -> dict:
        """Load raw account configuration dict."""
        account_dir = self.accounts_dir / account_id
        config_file = account_dir / "config.json"

        if not config_file.exists():
            raise FileNotFoundError(f"Account config not found: {config_file}")

        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_strategist_prompt(self, account_id: str) -> str:
        """
        Load strategist prompt for account

        Args:
            account_id: Account ID

        Returns:
            Strategist prompt text

        Raises:
            FileNotFoundError: If prompt file not found
        """
        account_dir = self.accounts_dir / account_id
        prompt_file = account_dir / "strategist_prompt.txt"

        if not prompt_file.exists():
            raise FileNotFoundError(f"Strategist prompt not found: {prompt_file}")

        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    def get_writer_prompt(self, account_id: str) -> str:
        """
        Load writer prompt for account

        Args:
            account_id: Account ID

        Returns:
            Writer prompt text

        Raises:
            FileNotFoundError: If prompt file not found
        """
        account_dir = self.accounts_dir / account_id
        prompt_file = account_dir / "writer_prompt.txt"

        if not prompt_file.exists():
            raise FileNotFoundError(f"Writer prompt not found: {prompt_file}")

        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    def list_accounts(self) -> list[str]:
        """
        List all available account IDs

        Returns:
            List of account IDs
        """
        accounts = []
        for item in self.accounts_dir.iterdir():
            if item.is_dir() and (item / "config.json").exists():
                accounts.append(item.name)

        return sorted(accounts)

    def get_all_accounts(self) -> list[Account]:
        """
        Load all accounts

        Returns:
            List of Account models
        """
        account_ids = self.list_accounts()
        accounts = []

        for account_id in account_ids:
            try:
                account = self.get_account(account_id)
                accounts.append(account)
            except Exception as e:
                logger.warning(f"Failed to load account {account_id}: {e}")

        return accounts
