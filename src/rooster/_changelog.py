from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Self, cast

import marko
import marko.ast_renderer
import marko.inline
import marko.md_renderer

from rooster._config import Config
from rooster._github import PullRequest
from rooster._versions import Version, get_previous_version, parse_versions

VERSION_HEADING_PREFIX = "## "


def new_heading(text: str, level: int = 1):
    return marko.parse("#" * level + " " + text + "\n").children[0]


class Section(abc.ABC):
    @abc.abstractclassmethod
    def new(
        cls, document: Document, element: marko.block.BlockElement, title: str
    ) -> Self:
        raise NotImplementedError

    @classmethod
    def from_elements(
        cls, document: Document, elements: list[marko.block.BlockElement], level: int
    ) -> list[Self]:
        renderer = document.renderer()
        sections = []
        last_section = None
        for element in elements:
            if isinstance(element, marko.block.Heading):
                if element.level < level:
                    last_section = None
                    continue
                if element.level > level:
                    if last_section:
                        last_section.children.append(element)
                    continue

                if element.children:
                    title = renderer.render(element.children[0])
                    entry = cls.new(document=document, element=element, title=title)
                    sections.append(entry)
                    last_section = entry
            elif isinstance(element, marko.block.BlankLine):
                continue
            else:
                if last_section:
                    last_section.children.append(element)

        return sections

    def print(self):
        renderer = self.document.renderer()
        if not hasattr(self.element, "link_ref_defs"):
            self.element.link_ref_defs = {}
        print(renderer.render(self.element), end="")
        for child in self.children:
            if isinstance(child, marko.block.BlankLine):
                print()
            else:
                # TODO: Report this as a bug upstream
                if not hasattr(child, "link_ref_defs"):
                    child.link_ref_defs = {}
                print(renderer.render(child), end="")


@dataclass
class Document:
    document: marko.block.Document

    @classmethod
    def from_markdown(cls, contents: str) -> Self:
        return cls(document=marko.parse(contents))

    @classmethod
    def from_file(cls, file: str | Path) -> Self:
        return cls.from_markdown(Path(file).read_text())

    def to_markdown(self) -> str:
        return self.renderer().render(self.document)

    def to_dict(self) -> dict:
        return marko.ast_renderer.ASTRenderer().render(self.document)

    def renderer(self) -> marko.md_renderer.MarkdownRenderer:
        renderer = marko.md_renderer.MarkdownRenderer()
        # Workaround for issues rendering links in children
        renderer.root_node = self.document
        return renderer

    @classmethod
    def empty(cls) -> Self:
        return cls(document=marko.block.Document())

    def add_child(self, child) -> None:
        self.document.children.append(child)

    def add_children(self, children) -> None:
        self.document.children.extend(children)


@dataclass
class Changelog(Document):
    def versions(self, level: int = 2) -> list[VersionSection]:
        """
        Extract version entries from the changelog.

        Each version is expected to be indicated by a header.

        By default, we expect versions to all be declared as level two headers.
        An alternative level can be requested.
        """
        return VersionSection.from_elements(self, self.document.children, level=level)

    def get_version_section(self, version: Version) -> VersionSection | None:
        for section in self.versions():
            if section.version == version:
                return section
        return None

    def insert_version_section(self, section: VersionSection, level: int = 2) -> None:
        renderer = self.renderer()
        elements = cast(list, self.document.children)
        remove = None
        for i, element in enumerate(tuple(elements)):
            if isinstance(element, marko.block.Heading):
                if element.level == level:
                    version = Version(renderer.render(element.children[0]))

                    # We got to the next heading
                    if remove:
                        remove.append(i)
                        break

                    # Assumes descending versions
                    if version < section.version:
                        break

                    # Replace the existing version
                    if version == section.version:
                        remove = [i]

        if remove:
            for _ in range(remove[0], remove[1]):
                elements.pop(remove[0])
            i = remove[0]

        elements.insert(i, section.element)
        elements.insert(i + 1, marko.block.BlankLine)

        # Insert all the version components
        offset = 0
        for offset, child in enumerate(section.children):
            elements.insert(i + 2 + offset, child)

        if not section.children:
            elements.insert(i + 2, marko.block.BlankLine)
            elements.insert(i + 2, marko.block.HTMLBlock("<!-- No changes -->"))

    @classmethod
    def new(cls) -> Self:
        new = cls.empty()
        new.add_child(new_heading("Changelog"))
        new.add_child(marko.block.BlankLine)
        new.add_child(marko.block.BlankLine)
        return new


@dataclass
class VersionSection(Section):
    document: Document
    element: marko.block.Heading
    title: str
    version: Version
    children: list[marko.parser.element.Element] = field(default_factory=list)

    @classmethod
    def new(
        cls, document: Document, element: marko.block.BlockElement, title: str
    ) -> Self:
        return cls(document, element, title, version=Version(title))

    def sections(self):
        """
        Extract entry sections from the version section.
        """
        # Sections are expected to be nested a single level deeper
        return EntrySection.from_elements(
            self.document, self.children, level=self.element.level + 1
        )

    def all_entries(self):
        entries = []
        for section in self.sections():
            entries.extend(section.entries())
        return entries

    @classmethod
    def from_pull_requests(
        cls,
        document: Document,
        config: Config,
        version: Version,
        pull_requests: Iterable[PullRequest],
        level: int = 2,
    ) -> Self:
        # Initialize the sections dictionary to match the changelog sections config for
        # ordering
        sections = {label: [] for label in config.changelog_sections}

        # De-duplicate pull requests and sort into sections
        for pull_request in set(pull_requests):
            for label in pull_request.labels:
                if label in config.changelog_ignore_labels:
                    break
            else:
                # Iterate in-order of changelog sections to support user-configured precedence
                for label in config.changelog_sections:
                    if label in pull_request.labels:
                        sections[label].append(pull_request)
                        break
                else:
                    sections["__unknown__"].append(pull_request)

        children = []
        for section, pull_requests in sections.items():
            # Omit empty sections
            if not pull_requests:
                continue

            pull_requests = sorted(pull_requests, key=lambda pr: pr.title)

            entry_section = EntrySection.from_pull_requests(
                document=document,
                config=config,
                section=section,
                pull_requests=pull_requests,
            )
            children.append(entry_section.element)
            children.extend(entry_section.children)

        heading_element = new_heading(str(version), level=level)

        return cls(
            document=document,
            element=heading_element,
            title=str(version),
            version=version,
            children=children,
        )

    def as_document(self) -> Document:
        document = Document.empty()
        document.add_child(self.element)
        document.add_child(marko.block.BlankLine)
        document.add_children(self.children)
        return document


@dataclass
class EntrySection(Section):
    document: Document
    element: marko.block.Heading
    title: str
    children: list[marko.parser.element.Element] = field(default_factory=list)

    @classmethod
    def new(
        cls, document: Document, element: marko.block.BlockElement, title: str
    ) -> Self:
        return cls(document, element, title)

    def entries(self):
        """ """
        entries = []
        for element in self.children:
            if isinstance(element, marko.block.List):
                for item in element.children:
                    entries.append(Entry(self.document, item))

        return entries

    @classmethod
    def from_pull_requests(
        cls,
        document: Document,
        config: Config,
        section: str,
        pull_requests: Iterable[PullRequest],
        level: int = 3,
    ) -> Self:
        title = config.changelog_sections.get(section)
        heading = new_heading(title, level)

        lines = []
        for pull_request in pull_requests:
            line = config.change_template.format(pull_request=pull_request)
            lines.append(line)

        return cls(
            document=document,
            element=heading,
            title=title,
            children=(
                [marko.block.BlankLine]
                + marko.parse("\n".join(lines)).children
                + [marko.block.BlankLine]
            ),
        )


@dataclass
class Entry:
    document: Document
    element: marko.block.ListItem

    def content(self) -> str:
        return self.document.renderer().render_children(self.element)


def generate_contributors(
    pull_requests: list[PullRequest], config: Config, level: int = 2
) -> str:
    contributors = ""
    authors = {
        pull_request.author
        for pull_request in pull_requests
        if pull_request.author not in config.changelog_ignore_authors
    }
    if authors:
        contributors += "#" * level + " Contributors\n"
        for author in sorted(authors):
            contributors += f"- [@{author}](https://github.com/{author})\n"
    return contributors


def ensure_spacing(changelog: str) -> str:
    # Sloppily ensure we don't have too much spacing
    while "\n\n\n" in changelog:
        changelog = changelog.replace("\n\n\n", "\n\n")

    # Ensure we always end with a single newline
    return changelog.rstrip("\n") + "\n"


def get_versions_from_changelog(changelog: str) -> list[Version]:
    """
    Get all versions from headings from the changelog
    """

    return parse_versions(
        [
            line[2:].strip()
            for line in changelog.splitlines()
            if line.startswith(VERSION_HEADING_PREFIX)
        ]
    )


def extract_entry(changelog: str, version: Version) -> str | None:
    """
    Extract an entry for the given version from the changelog
    """
    heading = f"{VERSION_HEADING_PREFIX}{version}\n\n"

    versions = get_versions_from_changelog(changelog)
    previous_version = get_previous_version(versions, version)

    # If there are no versions in the file, return `None`
    if not previous_version and heading not in changelog:
        return None

    previous_heading = (
        f"{VERSION_HEADING_PREFIX}{previous_version}\n\n" if previous_version else None
    )

    if heading not in changelog:
        return None

    start = changelog.index(heading)
    end = changelog.index(previous_heading) if previous_heading else len(changelog)
    return changelog[start:end]


def entry_to_standalone(changelog_entry: str, version: Version) -> str:
    """
    Convert an entry from the CHANGELOG file to a standalone entry (omitting the version)
    """
    return changelog_entry.replace(
        f"{VERSION_HEADING_PREFIX} {version}\n",
        f"{VERSION_HEADING_PREFIX} Changes\n<!-- Generated from the CHANGELOG file -->\n",
    )
