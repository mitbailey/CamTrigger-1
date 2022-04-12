CC=gcc
CFLAGS= -std=gnu11 -O2 -I gpiodev/ -I include/
LDFLAGS= -lm -lpthread

COBJS=src/main.o \
		gpiodev/gpiodev.o

all: $(COBJS)
	$(CC) -o record_data.out $(COBJS) $(LDFLAGS)
	sudo ./record_data.out

.PHONY: clean

clean:
	rm -vf $(COBJS)
	rm -vf *.out

spotless: clean
	rm -vf data/*