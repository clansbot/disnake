# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import (    Any,
    Dict,      Optional,   Set,
    Union,)

from . import utils
from .enums import Locale
from .errors import LocalizationLookupError

__all__ = (
    "Localized",
    "Localised",
    "LocalizedRequired",
    "LocalizedOptional",
    "LocalizationProtocol",
    "LocalizationStore",
)

_log = logging.getLogger(__name__)

@dataclass
class Localized:
    """A container type used for localized parameters.

    There is an alias for this called ``Localised``.

    .. versionadded:: 2.5

    Parameters
    ----------
    default: :class:`str`
        The default (non-localized) value of the string.
        Whether this is optional or not depends on the localized parameter type.
    key: Optional[:class:`str`]
        A localization key used for lookups.
    """

    __slots__ = ("default", "key")

    default: str
    key: Optional[str] = None

    @staticmethod
    def cast(src: str | Localized) -> Localized:
        if isinstance(src, str):
            return Localized(src)
        return src

Localised = Localized
LocalizedRequired = str | Localized
LocalizedOptional = LocalizedRequired | None

class LocalizationProtocol(ABC):
    """Manages a key-value mapping of localizations.

    This is an abstract class, a concrete implementation is provided as :class:`LocalizationStore`.

    .. versionadded:: 2.5
    """

    # TODO: relax this requirement
    @abstractmethod
    def available_languages(self) -> list[str | Locale]:
        raise NotImplementedError

    @abstractmethod
    def get(self, key: str, locale: str | Locale, *args: Any, **kwargs: Any) -> Optional[str]:
        """Returns localization for the specified key/locale pair.

        Parameters
        ----------
        key: :class:`str`
            The lookup key.
        locale: :class:`str` | :class:`Locale`
            The target locale.

        Raises
        ------
        LocalizationKeyError
            May be raised if no localization for the provided key/locale pair was found,
            depending on the implementation.

        Returns
        -------
        Optional[:class:`str`]
            The localization for the provided key/locale pair.
            May return ``None`` if no localization could be found.
        """
        raise NotImplementedError

    # subtypes don't have to implement this
    def load(self, path: Union[str, os.PathLike]) -> None:
        """Adds localizations from the provided path.

        Parameters
        ----------
        path: Union[:class:`str`, :class:`os.PathLike`]
            The path to the file/directory to load.

        Raises
        ------
        RuntimeError
            The provided path is invalid or couldn't be loaded.
        """
        raise NotImplementedError

    # subtypes don't have to implement this
    def reload(self) -> None:
        """Clears localizations and reloads all previously loaded sources again.
        If an exception occurs, the previous data gets restored and the exception is re-raised.
        """
        pass


class LocalizationStore(LocalizationProtocol):
    """Manages a key-value mapping of localizations using ``.json`` files.

    .. versionadded:: 2.5

    Attributes
    ----------
    strict: :class:`bool`
        Specifies whether :meth:`.get` raises an exception if localizations for a provided key couldn't be found.
    """

    def __init__(self, *, strict: bool) -> None:
        self.strict = strict

        # dict[locale, dict[key, localization]]
        self._localizations: Dict[str, Dict[str, str]] = {}
        self._paths: Set[Path] = set()

    def get(self, key: str, locale: str | Locale) -> Optional[str]:
        locale = locale if isinstance(locale, str) else locale.value

        try:
            return self._localizations[locale][key]
        except KeyError:
            if self.strict:
                raise LocalizationLookupError(key, locale) from None
            return None

    def load(self, path: Union[str, os.PathLike]) -> None:
        """Adds localizations from the provided path to the store.
        If the path points to a file, the file gets loaded.
        If it's a directory, all ``.json`` files in that directory get loaded (non-recursive).

        Parameters
        ----------
        path: Union[:class:`str`, :class:`os.PathLike`]
            The path to the file/directory to load.

        Raises
        ------
        RuntimeError
            The provided path is invalid or couldn't be loaded
        """
        path = Path(path)

        if not path.exists():
            raise RuntimeError(f"Path '{path}' does not exist.")

        if not (path.is_dir() or path.is_file()):
            raise RuntimeError(f"Path '{path}' is not a file or a directory.")

        self._paths.add(path)

        if path.is_file():
            self._load_file(path)
            return

        for entry in path.glob("*.json"):
            if not entry.is_file():
                continue
            self._load_file(entry)

    def reload(self) -> None:
        old = self._localizations

        try:
            self._localizations = {}
            for path in self._paths:
                self.load(path)
        except Exception:
            # restore in case of error
            self._localizations = old
            raise

    def _load_file(self, path: Path) -> None:
        if path.suffix != ".json":
            raise ValueError(f"'{path}' is not a .json file")

        if not (locale := utils.as_valid_locale(path.stem)):
            raise ValueError(f"'{path.stem}' is not a valid locale.")

        try:
            data: Dict[Any, Any] | Any = utils._from_json(path.read_text("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Unable to load contents of '{path}' as JSON: {e}")

        if not isinstance(data, dict):
            raise ValueError(f"Contents of '{path}' must be a plain JSON object.")

        for key, localization in data.items():
            if not isinstance(key, str):
                raise ValueError(f"Key '{key}' in file '{path}' must've been a string.")

            if not isinstance(localization, str):
                raise ValueError(f"Localization '{localization}' in file '{path}' must've been a string.")

            self._localizations[locale][key] = localization

        _log.debug(f"Loaded localizations from '{path}'")
