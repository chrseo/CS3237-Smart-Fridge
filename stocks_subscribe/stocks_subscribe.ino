#include <ArduinoMqttClient.h>
#include <ESP8266WiFi.h>
#include <WiFiClient.h>
#include "secret.h"

const char* ssid = SECRET_SSID; //Your Wifi's SSID
const char* password = SECRET_PASS; //Wifi Password

WiFiClient wifiClient;
MqttClient mqttClient(wifiClient);

const char* broker = "172.25.104.209";
int port = 1883;
const char* topic = "fridge/stock";

//set interval for sending messages (milliseconds)
const long interval = 10000;
unsigned long previousMillis = 0;

int count = 0;

void setup() {
  // put your setup code here, to run once:
  Serial.begin(9600);
  WiFi.begin(ssid, password);
  Serial.println("");

  Serial.print("Attempting to connect to WPA SSID: ");
  Serial.println(ssid);

  // Wait for connection
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.print("Connected to ");
  Serial.println(ssid);
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
  Serial.print("Attempting to connect to the MQTT broker: ");
  Serial.println(broker);

  if (!mqttClient.connect(broker, port)) {
    Serial.print("MQTT connection failed! Error code = ");
    Serial.println(mqttClient.connectError());
    while (1);
  }
  mqttClient.onMessage(onMqttMessage);
  mqttClient.subscribe(topic);
  Serial.println("You're connected to the MQTT broker!");
  Serial.println();
}

void onMqttMessage(int messageSize) {

  // we received a message, print out the topic and contents

  Serial.println("Received a message with topic '");
  Serial.print(mqttClient.messageTopic());
  Serial.print("', length ");
  Serial.print(messageSize);
  Serial.println(" bytes:");

  // use the Stream interface to print the contents
  while (mqttClient.available()) {
    Serial.print((char)mqttClient.read());
  }
  Serial.println();
  Serial.println();
}

void loop() {
  // put your main code here, to run repeatedly:
  
  // call poll() regularly to allow the library to send MQTT keep alive which
  // avoids being disconnected by the broker
  mqttClient.poll();
}
