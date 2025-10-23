import os
from datetime import datetime

try:
    import gnureadline as readline
except Exception:  # pragma: no cover - environment-dependent
    import readline  # type: ignore

# Initialize readline config if available
try:
    readline.read_init_file(os.path.expanduser("~/.inputrc"))
except Exception:
    pass
# Set delimiters to allow completion of workflow names with hyphens
readline.set_completer_delims(" \t\n`~!@#$%^&*()=+[{]}\\|;:'\",<>/?.")


def validate_float(v):
    try:
        return float(v)
    except ValueError:
        print("** Expecting float, got " + str(v))
        return None


def validate_date(v):
    v = v.strip()
    if len(v) == len("2021-10-20"):
        ymd = v.split("-")
        if len(ymd) != 3:
            print(f"** {v} does not look like a date, not 3 values")
            return None
    elif len(v) == len("20211020"):
        ymd = v[:4], v[4:6], v[6:]
    else:
        print(f"** {v} does not look like a date, " "not like 2021-10-20 or 20211020")
        return None

    try:
        y, m, d = [int(v) for v in ymd]
    except ValueError:
        print(f"** {v} does not look like a date, not 3 ints")
        return None

    min_year, max_year = 2021, datetime.today().year
    if not min_year <= y <= max_year:
        print("** Year %d not between %d and %d" % (y, min_year, max_year))
        return None

    try:
        datetime(y, m, d)
    except ValueError as e:
        print(f"** {v} not correct: {str(e)}")
        return None

    return "-".join(ymd)


class LineInput:
    def __init__(self, prompt, typical=None, only_typical=None, validator=None, with_history=True):
        self.prompt = prompt
        self.typical = typical if typical else []
        self.only_typical = only_typical if only_typical is not None else (len(self.typical) > 0)
        self.validator = validator
        self.with_history = with_history
        self.matches = []

        if with_history:
            history_dir = os.path.expanduser("~/.mailflow/history")
            if not os.path.exists(history_dir):
                os.makedirs(history_dir)
            self.history_file = os.path.join(
                history_dir, "history-" + prompt.lower().replace(" ", "-")
            )

            # When typical is not set we initialize it with the history
            if not typical and os.path.exists(self.history_file):
                readline.read_history_file(self.history_file)
                for i in range(readline.get_current_history_length()):
                    v = readline.get_history_item(i + 1)
                    if v not in self.typical:
                        self.typical.append(v)
        readline.clear_history()

    def complete(self, text, state):
        """It will be called with increasing numbers in state until it returns None"""
        if state == 0:
            # First call for this text, compute matches
            self.matches = sorted([t for t in self.typical if t.startswith(text)])

        # Return the state'th match
        if state < len(self.matches):
            return self.matches[state]
        return None

    def maybe_history_back(self):
        if self.with_history:
            readline.replace_history_item(readline.get_current_history_length() - 1, "")
            # readline.write_history_file(self.history_file)

    def ask(self, default=None):
        # Don't set up readline here - we'll do it after switching to tty if needed
        try:
            # Check if stdin is a pipe (e.g., from mutt)
            if not os.isatty(0):
                # Try to open /dev/tty for interactive input
                import sys

                # Save original stdin/stdout for error handling
                original_stdin = sys.stdin
                original_stdout = sys.stdout

                try:
                    # Save original file descriptors
                    old_stdin = os.dup(0)
                    old_stdout = os.dup(1)

                    # Open /dev/tty separately for reading and writing
                    tty_in = open("/dev/tty")
                    tty_out = open("/dev/tty", "w")

                    # Save terminal settings
                    import termios

                    old_settings = termios.tcgetattr(tty_in.fileno())

                    try:
                        # Critical: Update file descriptors 0 and 1 to use tty
                        # This ensures readline outputs to the right place
                        os.dup2(tty_in.fileno(), 0)  # stdin
                        os.dup2(tty_out.fileno(), 1)  # stdout

                        # Now set up readline - it will use the correct file descriptors
                        readline.clear_history()
                        readline.set_completer(self.complete)
                        readline.parse_and_bind("tab: complete")

                        if self.with_history and os.path.exists(self.history_file):
                            readline.read_history_file(self.history_file)

                        if default is not None:
                            v = input(f"{self.prompt} [default: {default}]: ")
                            if v == "":
                                v = default
                        else:
                            v = input(f"{self.prompt}: ")
                    finally:
                        # Restore original file descriptors
                        os.dup2(old_stdin, 0)
                        os.dup2(old_stdout, 1)
                        os.close(old_stdin)
                        os.close(old_stdout)

                        # Restore terminal settings
                        termios.tcsetattr(tty_in.fileno(), termios.TCSADRAIN, old_settings)
                        tty_in.close()
                        tty_out.close()
                except Exception:
                    # If /dev/tty fails, fall back to regular input
                    sys.stdin = original_stdin
                    sys.stdout = original_stdout
                    raise
            else:
                # Normal interactive mode
                readline.set_completer(self.complete)
                readline.clear_history()
                if self.with_history and os.path.exists(self.history_file):
                    readline.read_history_file(self.history_file)

                if default is not None:
                    v = input(f"{self.prompt} [default: {default}]: ")
                    if v == "":
                        v = default
                else:
                    v = input(f"{self.prompt}: ")

            if self.validator is not None:
                v = self.validator(v)
                if v is None:
                    self.maybe_history_back()
                    return self.ask(default)

            if v not in self.typical:
                if self.only_typical:
                    print("** Valid values are {} not {}".format(", ".join(self.typical), v))
                    self.maybe_history_back()
                    return self.ask(default)
                self.typical.append(str(v))
            return v
        finally:
            if self.with_history:
                readline.write_history_file(self.history_file)

    def _ask(self):
        readline.set_completer(self.complete)
        readline.clear_history()
        if self.with_history and os.path.exists(self.history_file):
            readline.read_history_file(self.history_file)

        try:
            v = input(f"{self.prompt}: ")
            if self.validator is not None:
                v = self.validator(v)
                if v is None:
                    self.maybe_history_back()
                    return self.ask()

            if v not in self.typical:
                if self.only_typical:
                    print("** Valid values are {} not {}".format(", ".join(self.typical), v))
                    self.maybe_history_back()
                    return self.ask()
                self.typical.append(str(v))
            return v
        finally:
            if self.with_history:
                readline.write_history_file(self.history_file)


class FloatInput(LineInput):
    def __init__(self, prompt):
        super().__init__(
            prompt,
            typical=None,
            only_typical=False,
            validator=validate_float,
            with_history=False,
        )


class DateInput(LineInput):
    def __init__(self, prompt, typical=None):
        if typical is None:
            typical = [datetime.today().strftime("%Y-%m-%d")]
        super().__init__(
            prompt,
            typical=typical,
            only_typical=False,
            validator=validate_date,
            with_history=True,
        )


if __name__ == "__main__":
    in_cat = LineInput("Category", ["personal", "business"])
    in_cur = LineInput("Currency", ["eur", "gbp", "usd"])
    in_date = DateInput("Date")
    in_amount = FloatInput("Amount")
    for _ in range(10):
        print(in_cat.ask())
        print(in_cur.ask())
        print(in_amount.ask())
        print(in_date.ask())
