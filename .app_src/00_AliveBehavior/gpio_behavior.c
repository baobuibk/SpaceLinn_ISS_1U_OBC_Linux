#include <gpiod.h>
#include <unistd.h>
#include <stdio.h>

#define GPIO_CHIP "/dev/gpiochip0"
#define INPUT_LINE 10
#define OUTPUT_LINE 24

int main() {
    struct gpiod_chip *chip;
    struct gpiod_line *in_line, *out_line;

    chip = gpiod_chip_open(GPIO_CHIP);
    if (!chip) {
        perror("Open chip failed");
        return 1;
    }

    in_line = gpiod_chip_get_line(chip, INPUT_LINE);
    out_line = gpiod_chip_get_line(chip, OUTPUT_LINE);

    gpiod_line_request_input(in_line, "gpio_in");
    gpiod_line_request_output(out_line, "gpio_out", 0);

    while (1) {
        int val = gpiod_line_get_value(in_line);
        gpiod_line_set_value(out_line, val);
        usleep(10000); // 10ms
    }

    gpiod_chip_close(chip);
    return 0;
}
