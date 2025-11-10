import base64

def generate_secret(output_file="secret.b64"):
    try:
        # Ask user to input the password
        password = input("Enter your password: ").strip()

        # Encode to Base64
        encoded = base64.b64encode(password.encode("utf-8")).decode("utf-8")

        # Write to output file
        with open(output_file, "w") as f:
            f.write(encoded)

        print(f"Successfully created {output_file}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate_secret()
