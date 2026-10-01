%global debug_package %{nil}
%global __brp_python_bytecompile %{nil}
%global __python %{__python3}

Name:           convertoor
Version:        %{?version_override}%{!?version_override:1.0.0}
Release:        1%{?dist}
Summary:        Drag-and-drop file converter
License:        MIT
URL:            https://github.com/calebtrueman/convertoor
Source0:        convertoor-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3 >= 3.8
Requires:       python3-gobject
Requires:       (gtk4 or typelib-1_0-Gtk-4_0)
Requires:       (libadwaita or typelib-1_0-Adw-1)
Requires:       /usr/bin/ffmpeg
Recommends:     ImageMagick
Recommends:     /usr/bin/pandoc
Recommends:     /usr/bin/pdftoppm
Recommends:     /usr/bin/rsvg-convert
Recommends:     (python3-pyyaml or python3-PyYAML)
Recommends:     python3-fonttools
Recommends:     /usr/bin/soffice
Suggests:       calibre
Suggests:       7zip

%description
Convertoor converts images, audio, video, documents, spreadsheets,
presentations, ebooks, archives, fonts and data files between formats.
Drop files on the window, pick a format and press Convert. It drives FFmpeg,
ImageMagick, Pandoc, LibreOffice, Poppler, librsvg, libheif, Calibre and
fontTools, chaining them automatically when needed.

%prep
%autosetup

%build

%install
DESTDIR=%{buildroot} PREFIX=%{_prefix} ./install.sh --no-deps

%files
%license LICENSE
%doc README.md
%{_bindir}/convertoor
%{_datadir}/convertoor/
%{_datadir}/applications/io.github.calebtrueman.Convertoor.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.calebtrueman.Convertoor.svg
%{_datadir}/metainfo/io.github.calebtrueman.Convertoor.metainfo.xml

%changelog
* Thu Oct 01 2026 Caleb Trueman <calebtrueman@users.noreply.github.com> - 1.0.0-1
- Initial release
