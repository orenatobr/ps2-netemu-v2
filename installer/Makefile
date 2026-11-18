#---------------------------------------------------------------------------------
# PS2 emulator patch installer for PS3 (PSL1GHT). Needs the ps3dev toolchain: export PS3DEV=<path> PSL1GHT=<path>.
# Needs payload/ps2_netemu_v2.bin first (see ../README.md).
#   make        builds PS2NetemuPatch.self
#   make pkg    builds PS2NetemuPatch.pkg (installable with "Install Package Files" on a CFW console)
#---------------------------------------------------------------------------------
.SUFFIXES:
#---------------------------------------------------------------------------------
MKROOT		:=	$(dir $(abspath $(firstword $(MAKEFILE_LIST))))

ifeq ($(strip $(PSL1GHT)),)
$(error "Please set PSL1GHT in your environment. export PSL1GHT=<path to ps3dev>")
endif

include $(PSL1GHT)/ppu_rules

#---------------------------------------------------------------------------------
# TARGET is the name of the output
# BUILD is the directory where object files & intermediate files will be placed
# SOURCES is a list of directories containing source code
# INCLUDES is a list of directories containing extra header files
# DATA is a list of directories with files linked into the binary (the fonts)
#---------------------------------------------------------------------------------
TARGET		:=	PS2NetemuPatch
BUILD		:=	build
SOURCES		:=	source
DATA		:=	data payload
INCLUDES	:=	source third_party/stb

# sha256 of the payload, compiled in so the installer refuses any other build
PATCHED_SHA256	:=	$(shell shasum -a 256 $(MKROOT)payload/ps2_netemu_v2.bin | cut -d' ' -f1)

# release version, the single source for the app title, the package version and the file names (../VERSION)
VERSION		:=	$(shell cat $(MKROOT)../VERSION)
APP_VER		:=	$(shell printf '%02d.%02d' $(word 1,$(subst ., ,$(VERSION))) $(word 2,$(subst ., ,$(VERSION))))

TITLE		:=	PS2 Emulator Patch
APPID		:=	PS2NMPTCH
CONTENTID	:=	UP0001-$(APPID)_00-0000000000000000
SFOXML		:=	$(MKROOT)build/sfo.xml
$(shell mkdir -p $(MKROOT)build && sed 's/@APP_VER@/$(APP_VER)/' $(MKROOT)pkg/sfo.xml > $(SFOXML))
ICON0		:=	$(MKROOT)build/ICON0.PNG
$(shell mkdir -p $(MKROOT)build && sh $(MKROOT)tools/icon.sh $(ICON0))
PKGFILES	:=	


#---------------------------------------------------------------------------------
# options for code generation
#---------------------------------------------------------------------------------
CFLAGS		=	-O2 -Wall -mcpu=cell $(MACHDEP) $(INCLUDE)
CXXFLAGS	=	$(CFLAGS) $(CXXFLAGS_INIT) -std=gnu++20 -DPATCHED_SHA256=\"$(PATCHED_SHA256)\" -DAPP_VERSION=\"$(VERSION)\"

LDFLAGS		=	$(MACHDEP) -Wl,-Map,$(notdir $@).map

LIBS		:=	-lrsx -lgcm_sys -lio -lsysutil -lrt -llv2 -lm

LIBDIRS		:=

#---------------------------------------------------------------------------------
# no real need to edit anything past this point unless you need to add additional
# rules for different file extensions
#---------------------------------------------------------------------------------
ifneq ($(BUILD),$(notdir $(CURDIR)))
#---------------------------------------------------------------------------------

export OUTPUT	:=	$(CURDIR)/$(TARGET)

export VPATH	:=	$(foreach dir,$(SOURCES),$(CURDIR)/$(dir)) \
					$(foreach dir,$(DATA),$(CURDIR)/$(dir))

export DEPSDIR	:=	$(CURDIR)/$(BUILD)

export BUILDDIR	:=	$(CURDIR)/$(BUILD)

CFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
CPPFILES	:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
sFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))
SFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.S)))
BINFILES	:=	$(foreach dir,$(DATA),$(notdir $(wildcard $(dir)/*.*)))

# use CXX for linking C++ projects, CC for standard C
ifeq ($(strip $(CPPFILES)),)
	export LD	:=	$(CC)
else
	export LD	:=	$(CXX)
endif

export OFILES	:=	$(addsuffix .o,$(BINFILES)) \
					$(CPPFILES:.cpp=.o) $(CFILES:.c=.o) \
					$(sFILES:.s=.o) $(SFILES:.S=.o)

export INCLUDE	:=	$(foreach dir,$(INCLUDES), -I$(CURDIR)/$(dir)) \
					$(foreach dir,$(LIBDIRS),-I$(dir)/include) \
					$(LIBPSL1GHT_INC) \
					-I$(CURDIR)/$(BUILD)

export LIBPATHS	:=	$(foreach dir,$(LIBDIRS),-L$(dir)/lib) \
					$(LIBPSL1GHT_LIB)

.PHONY: $(BUILD) clean pkg

all: $(BUILD)

$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

clean:
	@echo clean ...
	@rm -fr $(BUILD) $(OUTPUT).elf $(OUTPUT).self $(OUTPUT).fake.self $(OUTPUT).pkg $(OUTPUT).gnpdrm.pkg

run:
	ps3load $(OUTPUT).self

pkg: $(BUILD) $(OUTPUT).pkg

#---------------------------------------------------------------------------------
else

DEPENDS	:=	$(OFILES:.o=.d)

$(OUTPUT).self: $(OUTPUT).elf
$(OUTPUT).elf:	$(OFILES)

-include $(DEPENDS)

#---------------------------------------------------------------------------------
endif
#---------------------------------------------------------------------------------
