# Crypto_Assignment1_FPE
Naresh Gundu_CS21M514
Name: Naresh Gundu
Roll No: CS21M514

I have written FormatPreserveCipher class which encodes a string
within a range of minLen..maxLen. The spec uses an alternating Feistel.

More details on implementation algo:
FormatPreserveCipher initializes a new Cipher object for encryption or
decryption with key, tweak and radix parameters. The default radix is
10, supporting encryption of decimal numbers.
AES ECB (Assuming any encryption can be used for this assignment) is
used as the cipher round value for XORing. ECB has a block size of 128
bits (i.e 16 bytes) and is
padded with zeros for blocks smaller than this size. ECB is used only
in encrypt mode to generate this XOR value. A Feistel
decryption uses the same ECB encrypt value to decrypt the text.

Inputs:
plaintext = "652745"
Tweak = "401884"

Output:
Cipher Text ----> 939939

After decrypt:
Plain Text ---> 652745
