"""Entry point for the Smart Expense Tracker application."""

from income import add_income


def main() -> None:
    """Run the application."""
    print("=== Smart Expense Tracker ===")

    try:
        income = add_income(
            amount=1500.0,
            category="Salary",
            account="Bank Account",
            description="July salary",
        )
    except ValueError as error:
        print(f"Error: {error}")
        return

    print("Income created successfully:")
    print(income)


if __name__ == "__main__":
    main()
