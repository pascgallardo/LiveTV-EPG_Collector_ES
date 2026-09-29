"""Generate the per-section index files consumed by index.html.

Each section directory (LiveTV/, Movies/, ...) gets an index.json listing its
sub-directories, sorted alphabetically. Missing sections are skipped instead of
failing the run.
"""
import json
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SECTIONS = ['LiveTV', 'Movies']


def generate_index(folder, output_file):
    """Write the sorted list of sub-directories of *folder* to *output_file*."""
    if not os.path.isdir(folder):
        logging.warning(f"Skipping {folder}: directory not found")
        return False
    subdirs = [d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))]
    subdirs.sort()
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(subdirs, f, indent=2, ensure_ascii=False)
        f.write('\n')
    logging.info(f"Wrote {output_file} with {len(subdirs)} entries")
    return True


def main():
    for section in SECTIONS:
        generate_index(section, os.path.join(section, 'index.json'))


if __name__ == '__main__':
    main()
