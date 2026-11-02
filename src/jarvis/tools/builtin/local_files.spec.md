# Local files tool

`localFiles` reads, lists, creates and appends text notes locally. It does not call an LLM or a network service. Paths are expanded and resolved before use, and the resolved target must be the configured notes folder (`local_files_root`, default the home directory) or a descendant. Relative paths resolve against that folder.

- `operation` and `path` are required. Supported operations are `list`, `read`, `write` and `append`. `delete` is refused: Jarvis never deletes a file, and the reply asks the user to delete it themselves.
- `path` must be a non-empty JSON string. Numbers, booleans, arrays and objects return a correctable error before path resolution or file access. Relative paths, including numeric filenames represented as strings, are supported.
- Write and append require string `content`, which is stored literally as UTF-8. Both accept only `.md` and `.txt` files, so scripts and executables cannot be created even inside the notes folder.
- Write creates a new note and its parent directories. It refuses an existing file and suggests appending or a new name, so an existing note is never overwritten. Append adds to the end of an existing note.
- Listings use `glob` (default `*`). `recursive` defaults to false and must be a JSON boolean when supplied. Strings, numbers, null, arrays and objects return a correctable tool error without producing a listing.
- False and omitted recursion apply the supplied glob to the target directory. True recursion applies the pattern recursively. Listings show at most 50 sorted entries and report the count of additional entries.
- Listing directory prefixes and each matched entry's parent must resolve within the notes folder. Expanded intermediate directories and links are checked before the next pattern component can inspect them, independently of whether the final filename exists. Patterns cannot expose filenames through external parents or directory links. Symbolic link entries in directory listings are labelled `LINK` using metadata that does not follow their targets. In-folder parent selectors and directory links retain their matching behaviour. Listing failures return a generic correction hint without external filenames or resolved paths.
- Reads return at most 10,000 characters, with an explicit truncation marker for longer text. Invalid UTF-8 is replaced.
- Errors return unsuccessful tool results. The reply engine decides how to explain errors or request corrected arguments.
