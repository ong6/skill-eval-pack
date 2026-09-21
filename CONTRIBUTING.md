# Contributing

Bug reports and focused fixes are welcome. Open an issue before changing the evaluation contract or
file formats; backward compatibility and the blind-comparison boundary are part of the design.

Run both checks before opening a pull request:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash tests/test_install.sh
```

Keep evaluation artifacts out of the repository. They may contain private prompts, transcripts and
model output.
