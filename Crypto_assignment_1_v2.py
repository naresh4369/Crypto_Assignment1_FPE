
# coding: utf-8

# In[3]:


import logging
import math
import string
from Crypto.Cipher import AES



NUM_ROUNDS = 8
BLOCK_SIZE = 16  # aes.BlockSize
TWEAK_LEN = 8  # Original tweak length
TWEAK_LEN_NEW = 7  # tweak length
HALF_TWEAK_LEN = TWEAK_LEN // 2
MAX_RADIX = 36  # python int supports radix 2..36
DOMAIN_MIN = 1000000  # 1M required in FF3-1

def reverse_string(str):
    """func defined for clarity"""
    return str[::-1]



class FormatPreserveCipher:
    """Class FF3Cipher implements the FF3 format-preserving encryption algorithm"""
    def __init__(self, key, tweak, radix=10, ):

        keyBytes = bytes.fromhex(key)
        self.tweak = tweak
        self.radix = radix

        # Calculate range of supported message lengths [minLen..maxLen]
        #  radix^minLength >= 100.
        self.minLen = math.ceil(math.log(DOMAIN_MIN) / math.log(radix))

        # simplify with log[radix](2^96) to 96/log2(radix) using the log base change rule
        self.maxLen = 2 * math.floor(96/math.log2(radix))

        klen = len(keyBytes)

        # Check if the key is 128, 192, or 256 bits = 16, 24, or 32 bytes
        if klen not in (16, 24, 32):
            raise ValueError(f'key length is {klen} but must be 128, 192, or 256 bits')

        #  radices in [2, 2^16], there is a practical limit to 36 (alphanumeric)
        # because python int only supports up to base 36.
        if (radix < 2) or (radix > MAX_RADIX):
            raise ValueError("radix must be between 2 and 36, inclusive")

        # Make sure 2 <= minLength <= maxLength
        if (self.minLen < 2) or (self.maxLen < self.minLen):
            raise ValueError("minLen or maxLen invalid, adjust your radix")

        # AES block cipher in ECB mode with the block size derived based on the length of the key
        # Always use the reversed key since Encrypt and Decrypt call ciph expecting that

        self.aesCipher = AES.new(reverse_string(keyBytes), AES.MODE_ECB)

    @staticmethod
    def calculateP(i, radix, W, B):
        # P is always 16 bytes
        P = bytearray(BLOCK_SIZE)

        # Calculate P by XORing W, i into the first 4 bytes of P
        # i only requires 1 byte, rest are 0 padding bytes
        # Anything XOR 0 is itself, so only need to XOR the last byte

        P[0] = W[0]
        P[1] = W[1]
        P[2] = W[2]
        P[3] = W[3] ^ int(i)

        # The remaining 12 bytes of P are for rev(B) with padding

        numB = reverse_string(B)
        numBBytes = int(numB, radix).to_bytes(12, "big")
        # logging.debug(f"B: {B} numB: {numB} numBBytes: {numBBytes.hex()}")

        P[BLOCK_SIZE - len(numBBytes):] = numBBytes
        return P

    def encrypt(self, plaintext):
        """Encrypts the plaintext string and returns a ciphertext of the same length and format"""
        return self.encrypt_with_tweak(plaintext, self.tweak)

    """
    Feistel structure
            u length |  v length
            A block  |  B block
                C <- modulo function
            B' <- C  |  A' <- B
    Steps:
    Let u = [n/2]
    Let v = n - u
    Let A = X[1..u]
    Let B = X[u+1,n]
    Let T(L) = T[0..31] and T(R) = T[32..63]
    for i <- 0..7 do
        If is even, let m = u and W = T(R) Else let m = v and W = T(L)
        Let P = REV([NUM<radix>(Rev(B))]^12 || W ⊗ REV(i^4)
        Let Y = CIPH(P)
        Let y = NUM<2>(REV(Y))
        Let c = (NUM<radix>(REV(A)) + y) mod radix^m
        Let C = REV(STR<radix>^m(c))
        Let A = B
        Let B = C
    end for
    Return A || B
   
    """

    # EncryptWithTweak allows a parameter tweak instead of the current Cipher's tweak

    def encrypt_with_tweak(self, plaintext, tweak):
        """Encrypts the plaintext string and returns a ciphertext of the same length and format"""
        tweakBytes = bytes.fromhex(tweak)

        n = len(plaintext)

        # Check if message length is within minLength and maxLength bounds
        if (n < self.minLen) or (n > self.maxLen):
            raise ValueError(f"message length {n} is not within min {self.minLen} and max {self.maxLen} bounds")

        # Make sure the given the length of tweak in bits is 56 or 64
        if len(tweakBytes) not in [TWEAK_LEN, TWEAK_LEN_NEW]:
            raise ValueError(f"tweak length {len(tweakBytes)} invalid: tweak must be 56 or 64 bits")

        # Convert the plaintext message string into an integer
        x = int(plaintext, self.radix)

        # Calculate split point
        u = math.ceil(n / 2)
        v = n - u

        # Split the message
        A = plaintext[:u]
        B = plaintext[u:]

        if len(tweakBytes) == TWEAK_LEN:
            # Split the tweak
            Tl = tweakBytes[:HALF_TWEAK_LEN]
            Tr = tweakBytes[HALF_TWEAK_LEN:]
        elif len(tweakBytes) == TWEAK_LEN_NEW:
            # Tl is T[0..27] + 0000
            Tl = bytearray(tweakBytes[:4])
            Tl[3] &= 0xF0

            # Tr is T[32..55] + T[28..31] + 0000
            Tr = bytearray((int(tweakBytes[4:].hex(), 16) << 4).to_bytes(4, 'big'))
            Tr[3] = tweakBytes[6] << 4 & 0xF0
        else:
            raise ValueError(f"tweak length {len(tweakBytes)} invalid: tweak must be 56 or 64 bits")

        logging.debug(f"Tweak: {tweak}, tweakBytes:{tweakBytes.hex()}")

        # P is always 16 bytes
        # P = bytearray(BLOCK_SIZE)

        # Pre-calculate the modulus since it's only one of 2 values,
        # depending on whether i is even or odd

        modU = self.radix ** u
        modV = self.radix ** v
        logging.debug(f"modU: {modU} modV: {modV}")

        # Main Feistel Round, 8 times
        #
        # AES ECB requires the number of bits in the plaintext to be a multiple of
        # the block size. Thus, we pad the input to 16 bytes

        for i in range(NUM_ROUNDS):
            # logging.debug(f"-------- Round {i}")
            # Determine alternating Feistel round side
            if i % 2 == 0:
                m = u
                W = Tr
            else:
                m = v
                W = Tl

            # P is fixed-length 16 bytes
            P = FormatPreserveCipher.calculateP(i, self.radix, W, B)
            revP = reverse_string(P)

            S = self.aesCipher.encrypt(bytes(revP))

            S = reverse_string(S)
            # logging.debug("S:    ", S.hex())

            y = int.from_bytes(S, byteorder='big')

            # Calculate c
            c = int(reverse_string(A), self.radix)

            c = c + y

            if i % 2 == 0:
                c = c % modU
            else:
                c = c % modV

            # logging.debug(f"m: {m} A: {A} c: {c} y: {y}")
            C = base_conv_r(c, self.radix, int(m))

            # Final steps
            A = B
            B = C

            # logging.debug(f"A: {A} B: {B}")

        return A + B

    def decrypt(self, ciphertext):
        """
        Decrypts the ciphertext string and returns a plaintext of the same length and format.
        The process of decryption is essentially the same as the encryption process. The  differences
        are  (1)  the  addition  function  is  replaced  by  a  subtraction function that is its
        inverse, and (2) the order of the round indices (i) is reversed.
        """
        return self.decrypt_with_tweak(ciphertext, self.tweak)

    def decrypt_with_tweak(self, ciphertext, tweak):
        """Decrypts the ciphertext string and returns a plaintext of the same length and format"""
        tweakBytes = bytes.fromhex(tweak)

        n = len(ciphertext)

        # Check if message length is within minLength and maxLength bounds
        if (n < self.minLen) or (n > self.maxLen):
            raise ValueError(f"message length {n} is not within min {self.minLen} and max {self.maxLen} bounds")

        # Make sure the given the length of tweak in bits is 56 or 64
        if len(tweakBytes) not in [TWEAK_LEN, TWEAK_LEN_NEW]:
            raise ValueError(f"tweak length {len(tweakBytes)} invalid: tweak must be 8 bytes, or 64 bits")

        # Convert the ciphertext message string into an integer
        x = int(ciphertext, self.radix)

        # Calculate split point
        u = math.ceil(n/2)
        v = n - u

        # Split the message
        A = ciphertext[:u]
        B = ciphertext[u:]

        # Split the tweak
        if len(tweakBytes) == TWEAK_LEN:
            # Split the tweak
            Tl = tweakBytes[:HALF_TWEAK_LEN]
            Tr = tweakBytes[HALF_TWEAK_LEN:]
        elif len(tweakBytes) == TWEAK_LEN_NEW:
            # Tl is T[0..27] + 0000
            Tl = bytearray(tweakBytes[:4])
            Tl[3] &= 0xF0

            # Tr is T[32..55] + T[28..31] + 0000
            Tr = bytearray((int(tweakBytes[4:].hex(), 16) << 4).to_bytes(4, 'big'))
            Tr[3] = tweakBytes[6] << 4 & 0xF0
        else:
            raise ValueError(f"tweak length {len(tweakBytes)} invalid: tweak must be 56 or 64 bits")

        logging.debug(f"Tweak: {tweak}, tweakBytes:{tweakBytes.hex()}")

        # P is always 16 bytes
        # P = bytearray(BLOCK_SIZE)

        # Pre-calculate the modulus since it's only one of 2 values,
        # depending on whether i is even or odd

        modU = self.radix ** u
        modV = self.radix ** v
        logging.debug(f"modU: {modU} modV: {modV}")

        # Main Feistel Round, 8 times

        for i in reversed(range(NUM_ROUNDS)):

            # logging.debug(f"-------- Round {i}")
            # Determine alternating Feistel round side
            if i % 2 == 0:
                m = u
                W = Tr
            else:
                m = v
                W = Tl

            # P is fixed-length 16 bytes
            P = FormatPreserveCipher.calculateP(i, self.radix, W, A)
            revP = reverse_string(P)

            S = self.aesCipher.encrypt(bytes(revP))
            S = reverse_string(S)

            # logging.debug("S:    ", S.hex())

            y = int.from_bytes(S, byteorder='big')

            # Calculate c
            c = int(reverse_string(B), self.radix)

            c = c - y

            if i % 2 == 0:
                c = c % modU
            else:
                c = c % modV

            # logging.debug(f"m: {m} B: {B} c: {c} y: {y}")
            C = base_conv_r(c, self.radix, int(m))

            # Final steps
            B = A
            A = C

            # logging.debug(f"A: {A} B: {B}")

        return A + B


DIGITS = string.digits + string.ascii_lowercase 
LEN_DIGITS = len(DIGITS)


def base_conv_r(n, base=2, length=0):    
    """
    Return a string representation of a number in the given base system for 2..36
    The string is left in a reversed order expected by the calling cryptographic function
    """

    x = ''
    while n >= base:
        n, b = divmod(n, base)
        x += DIGITS[b]
    x += DIGITS[n]

    if len(x) < length:
        x = x.ljust(length, '0')

    return x


# In[38]:


Key = "EF4359D8D580AA4F7F036D6F04FC6A94"
Tweak = "401884"

len_tweak = len(Tweak)
prefix = ""

for i in range(0,16-len_tweak):
    prefix = prefix + "0"
    
final_tweak = prefix+Tweak
print(final_tweak)

c = FormatPreserveCipher(Key,final_tweak)

plaintext = "652745"

print("Plaintext before encryption --->",plaintext)
ct = c.encrypt(plaintext)

print("Cipher Text after encryption ---->",ct)
pt = c.decrypt(ct)
print("Plain Text after decryption --->",pt)

