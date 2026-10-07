"""
Trie implementation for X Language
"""
from typing import Any


class TrieClass:
    """X language Trie class implementation"""
    
    def __init__(self):
        self.data = {"children": {}, "is_end": False, "count": 0}
    
    def insert(self, word: str) -> None:
        """Insert a word"""
        if not isinstance(word, str):
            raise Exception("Trie.insert word must be a string")
        node = self.data
        for char in word:
            if char not in node["children"]:
                node["children"][char] = {"children": {}, "is_end": False}
            node = node["children"][char]
        if not node["is_end"]:
            node["is_end"] = True
            self.data["count"] = self.data.get("count", 0) + 1
    
    def search(self, word: str) -> bool:
        """Check if exact word exists"""
        if not isinstance(word, str):
            raise Exception("Trie.search word must be a string")
        node = self.data
        for char in word:
            if char not in node["children"]:
                return False
            node = node["children"][char]
        return node.get("is_end", False)
    
    def startsWith(self, prefix: str) -> bool:
        """Check if any word starts with prefix"""
        if not isinstance(prefix, str):
            raise Exception("Trie.startsWith prefix must be a string")
        node = self.data
        for char in prefix:
            if char not in node["children"]:
                return False
            node = node["children"][char]
        return True
    
    def remove(self, word: str) -> bool:
        """Remove a word"""
        if not isinstance(word, str):
            raise Exception("Trie.remove word must be a string")
        
        def _remove_helper(node: dict, word: str, index: int) -> bool:
            if index == len(word):
                if not node.get("is_end", False):
                    return False
                node["is_end"] = False
                self.data["count"] = self.data.get("count", 0) - 1
                return len(node["children"]) == 0
            char = word[index]
            if char not in node["children"]:
                return False
            should_delete = _remove_helper(node["children"][char], word, index + 1)
            if should_delete:
                del node["children"][char]
                return len(node["children"]) == 0 and not node.get("is_end", False)
            return False
        
        return _remove_helper(self.data, word, 0)
    
    def size(self) -> int:
        """Return word count"""
        return self.data.get("count", 0)
    
    def isEmpty(self) -> bool:
        """Check if empty"""
        return self.data.get("count", 0) == 0
    
    def clear(self) -> None:
        """Clear all words"""
        self.data = {"children": {}, "is_end": False, "count": 0}
    
    def getAllWords(self) -> list[str]:
        """Return all words"""
        words = []
        
        def _collect_words(node: dict, prefix: str) -> None:
            if node.get("is_end", False):
                words.append(prefix)
            for char, child in node["children"].items():
                _collect_words(child, prefix + char)
        
        _collect_words(self.data, "")
        return words

    def getWordsWithPrefix(self, prefix: str) -> list[str]:
        """Return all words that begin with *prefix*.

        Traverses to the node corresponding to the last character of *prefix*;
        returns an empty list when no such prefix exists in the trie.  Then
        runs a DFS from that node to collect every complete word, seeding each
        result with the supplied prefix string.

        Args:
            prefix: The prefix string to search for.

        Returns:
            A list of words (possibly empty) that all start with *prefix*.
        """
        if not isinstance(prefix, str):
            raise Exception("Trie.getWordsWithPrefix: prefix must be a string")
        node: dict = self.data
        for char in prefix:
            if char not in node["children"]:
                return []
            node = node["children"][char]

        words: list[str] = []

        def _collect(current_node: dict, current_prefix: str) -> None:
            if current_node.get("is_end", False):
                words.append(current_prefix)
            for char, child in current_node["children"].items():
                _collect(child, current_prefix + char)

        _collect(node, prefix)
        return words
