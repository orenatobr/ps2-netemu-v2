// Small POSIX file helpers shared by every module (work on the console and on the host).
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace fsx {

/// Reads a whole file as text. Returns false when it cannot be read.
bool readFile(const std::string& path, std::string& out);

/// Reads a whole file as bytes. Returns false when it cannot be read or is larger than `maxBytes`.
bool readBytes(const std::string& path, std::vector<std::uint8_t>& out, std::size_t maxBytes = 64u * 1024 * 1024);

/// Writes a file, replacing it. Returns false on any short write.
bool writeBytes(const std::string& path, const std::vector<std::uint8_t>& data);

/// Copies a file. Returns false when the source cannot be read or the copy is short.
bool copyFile(const std::string& from, const std::string& to);

/// Creates a directory and its parents. Returns true when it exists afterwards.
bool makeDirs(const std::string& path);

/// True when the path can be opened for reading (file or directory).
bool exists(const std::string& path);

/// True when the path is a directory.
bool isDir(const std::string& path);

/// Names (not paths) inside a directory, without "." and "..", sorted.
std::vector<std::string> listDir(const std::string& path);

/// Renames a file, replacing the target when it already exists.
bool renameFile(const std::string& from, const std::string& to);

/// Deletes a file. Returns true when it no longer exists.
bool removeFile(const std::string& path);

/// 32-bit FNV-1a hash, used to verify a written file by reading it back.
std::uint32_t fnv1a(const std::vector<std::uint8_t>& data);

/// 32-bit FNV-1a hash of a string (stable ids for paths).
std::uint32_t fnv1a(const std::string& text);

}  // namespace fsx
