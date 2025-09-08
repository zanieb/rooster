from __future__ import annotations

import abc
import copy
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Self, cast

import marko
import marko.ast_renderer
import marko.inline
import marko.md_renderer

from rooster._config import Config
from rooster._github import PullRequest
from rooster._versions import (
    Version,
    get_previous_version,
    parse_version,
    to_cargo_version,
)

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

    def get_version_section(
        self, config: Config, version: Version
    ) -> VersionSection | None:
        for section in self.versions():
            if section.version == (
                to_cargo_version(version)
                if config.version_format == "cargo"
                else str(version)
            ):
                return section
        return None

    def insert_version_section(self, section: VersionSection, level: int = 2) -> None:
        renderer = self.renderer()
        elements = cast(list, self.document.children)
        remove = None
        i = 0

        # Scan for an existing version
        for i, element in enumerate(tuple(elements)):
            # Append items to remove...
            if remove:
                remove.append(i)

            if isinstance(element, marko.block.Heading):
                if element.level == level:
                    title = renderer.render(element.children[0])

                    # We got to the next version heading
                    if remove:
                        # Don't remove the next version
                        remove.pop()
                        break

                    # Replace the existing version
                    if title == section.version:
                        remove = [i]
        if remove:
            # As we remove each item, the index of the next item to remove will change
            for i, to_remove in enumerate(sorted(remove)):
                elements.pop(to_remove - i)
            i = remove[0]
        else:
            # Scan for an insertion position
            try:
                compare_version = Version(section.version)
            except Exception:
                # We cannot compare in this case
                compare_version = None

            for i, element in enumerate(tuple(elements)):
                if not isinstance(element, marko.block.Heading):
                    continue
                if element.level != level:
                    continue

                # If we can't compare versions, just stop at the top
                if not compare_version:
                    break

                try:
                    version = Version(renderer.render(element.children[0]))
                except Exception:
                    # We encountered an invalid version, stop here
                    break

                # Otherwise, stop at the first smaller version
                if version < compare_version:
                    break

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
    version: str
    children: list[marko.parser.element.Element] = field(default_factory=list)

    @classmethod
    def new(
        cls, document: Document, element: marko.block.BlockElement, title: str
    ) -> Self:
        return cls(document, element, title, version=title)

    def sections(self):
        """
        Extract entry sections from the version section.
        """
        # Sections are expected to be nested a single level deeper
        return ChangesSection.from_elements(
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
        only_sections: set[str],
        without_sections: set[str],
        level: int = 2,
        release_date: date | None = None,
    ) -> Self:
        section_labels = defaultdict(list, copy.deepcopy(config.section_labels))

        # Backwards compatibility
        for label, section in config.changelog_sections.items():
            section_labels[section].append(label)

        # Initialize the sections dictionary to match the config ordering
        sections = {section: [] for section in section_labels.keys()}

        # If there are no sections, put all changes into "Changes", otherwise,
        # use `Other changes`
        other_section = "Other changes" if sections else "Changes"
        sections[other_section] = []

        authors = {
            pull_request.author
            for pull_request in pull_requests
            if pull_request.author not in config.changelog_ignore_authors
        }

        # De-duplicate pull requests and sort into sections
        for pull_request in sorted(set(pull_requests)):
            for label in pull_request.labels:
                if label in config.changelog_ignore_labels:
                    break
                if label in without_sections:
                    break
            else:
                # Iterate in-order of changelog sections to support user-configured precedence
                for section, labels in section_labels.items():
                    if only_sections and section not in only_sections:
                        continue
                    if pull_request.labels.intersection(labels):
                        sections[section].append(pull_request)
                        break
                else:
                    if not only_sections:
                        sections[
                            section_labels.get("__unknown__", other_section)
                        ].append(pull_request)

        children = []
        for section, pull_requests in sections.items():
            # Omit empty sections
            if not pull_requests:
                continue

            pull_requests = sorted(pull_requests, key=lambda pr: pr.title)

            changes_section = ChangesSection.from_pull_requests(
                document=document,
                config=config,
                section=section,
                pull_requests=pull_requests,
            )
            children.append(changes_section.element)
            children.extend(changes_section.children)

        if config.changelog_contributors and authors:
            section = ContributorsSection.from_authors(
                document=document, authors=authors
            )
            children.append(section.element)
            children.extend(section.children)

        version = (
            to_cargo_version(version)
            if config.version_format == "cargo"
            else str(version)
        )
        heading_element = new_heading(version, level=level)

        # Add release date paragraph
        if release_date is None:
            release_date = date.today()
        date_str = release_date.strftime("%Y-%m-%d")
        release_date_text = f"Released on {date_str}."
        release_date_paragraph = marko.parse(release_date_text + "\n").children[0]

        # Insert release date at the beginning of children
        all_children = [release_date_paragraph, marko.block.BlankLine] + children

        return cls(
            document=document,
            element=heading_element,
            title=version,
            version=version,
            children=all_children,
        )

    def as_document(self) -> Document:
        document = Document.empty()
        document.add_child(self.element)
        document.add_child(marko.block.BlankLine)
        document.add_children(self.children)
        return document


@dataclass
class ListSection(Section):
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


@dataclass
class ChangesSection(ListSection):
    @classmethod
    def from_pull_requests(
        cls,
        document: Document,
        config: Config,
        section: str,
        pull_requests: Iterable[PullRequest],
        level: int = 3,
    ) -> Self:
        heading = new_heading(section, level)

        lines = []
        for pull_request in pull_requests:
            line = config.change_template.format(pull_request=pull_request)
            lines.append(line)

        return cls(
            document=document,
            element=heading,
            title=section,
            children=(
                [marko.block.BlankLine]
                + marko.parse("\n".join(lines)).children
                + [marko.block.BlankLine]
            ),
        )


@dataclass
class ContributorsSection(ListSection):
    @classmethod
    def from_authors(
        cls,
        document: Document,
        authors: Iterable[PullRequest],
        level: int = 3,
    ) -> Self:
        heading = new_heading("Contributors", level)

        lines = []
        for author in authors:
            line = f"- [@{author}](https://github.com/{author})"
            lines.append(line)

        return cls(
            document=document,
            element=heading,
            title="Contributors",
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


def ensure_spacing(changelog: str) -> str:
    # Sloppily ensure we don't have too much spacing
    while "\n\n\n" in changelog:
        changelog = changelog.replace("\n\n\n", "\n\n")

    # Ensure we always end with a single newline
    return changelog.rstrip("\n") + "\n"


def get_versions_from_changelog(config: Config, changelog: str) -> list[Version]:
    """
    Get all versions from headings from the changelog
    """

    return filter(
        lambda x: x is not None,
        [
            parse_version(config, line[2:].strip())
            for line in changelog.splitlines()
            if line.startswith(VERSION_HEADING_PREFIX)
        ],
    )


def extract_entry(config: Config, changelog: str, version: Version) -> str | None:
    """
    Extract an entry for the given version from the changelog
    """
    version_str = (
        to_cargo_version(version) if config.version_format == "cargo" else str(version)
    )
    heading = f"{VERSION_HEADING_PREFIX}{version_str}\n\n"

    versions = get_versions_from_changelog(config, changelog)
    previous_version = get_previous_version(versions, version)

    # If there are no versions in the file, return `None`
    if not previous_version and heading not in changelog:
        return None

    previous_version_str = (
        (
            to_cargo_version(version)
            if config.version_format == "cargo"
            else str(version)
        )
        if previous_version
        else None
    )
    previous_heading = (
        f"{VERSION_HEADING_PREFIX}{previous_version_str}\n\n"
        if previous_version
        else None
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
